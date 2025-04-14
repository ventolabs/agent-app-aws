import json
import math
from os import getenv
from typing import Optional, List

import requests

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger

from tools.config import settings
from tools.crypto.waves.exceptions import WavesException, WavesInvalidResponse, WavesInvalidAsset
from tools.crypto.waves.tokens import TOKENS

try:
    import pywaves as pw
except ImportError:
    raise ImportError("`pywaves` not installed. Please install using `pip install pywaves`.")


class WavesUsdtTools(Toolkit):
    """
    Waves Usdt Tools is a toolkit for interacting with the Waves blockchain to get information about USDT assets and Puzzle Lend pools. 
    It provides functionality to:
    1. Get information about USDT assets across all Puzzle Lend pools.
    2. Get the supply of all assets in the wallet.
    3. Get the balance of USDT for an address.
    4. Stake assets in a Puzzle Lend USDT liquidity pool.
    5. Unstake (withdraw) assets from a Puzzle Lend USDT liquidity pool.
    6. Swap tokens using the Puzzle Swap aggregator.
    
    Args:
        node (str): Waves node URL
        chain (str): Chain to use (mainnet/testnet)
        private_key (Optional[str]): Private key for transaction signing
        wallet_address (Optional[str]): Wallet address to use for transaction signing
    """

    def __init__(
        self,
        node: str = "https://nodes.wavesnodes.com",
        chain: str = "mainnet",
        private_key: Optional[str] = None,
        wallet_address: Optional[str] = None
    ):
        super().__init__(name="waves_tools")

        # Initialize PyWaves configuration
        pw.setNode(node=node, chain=chain)

        # Get private key from environment variable
        self.private_key = settings.waves.waves_private_key or getenv("WAVES_PRIVATE_KEY")
        self.wallet_address = settings.waves.waves_address or getenv("WAVES_ADDRESS")
        if not self.private_key and not self.wallet_address:
            logger.error("Waves private key or address is required")
            raise ValueError("Waves private key or address is required")
            
        # Set up wallet if private key is provided
        self.address = None
        if self.private_key:
            self.address = pw.Address(privateKey=self.private_key)
        elif self.wallet_address:
            self.address = pw.Address(address=self.wallet_address)
            
        self.node = node
        self.chain = chain

        # Register functions
        self.register(self.get_puzzle_lend_wallet_supply) 
        self.register(self.get_puzzle_lend_usdt_pools) 
        self.register(self.puzzle_lend_supply_assets)
        self.register(self.puzzle_lend_withdraw_assets)
        self.register(self.get_wallet_usdt_balance)
        self.register(self.puzzle_swap_tokens)

    def evaluate_smart_contract(self, expr: str) -> str:
        """
        Evaluate an expression on a smart contract using Waves node API.
        
        Args:
            expr (str): The expression to evaluate
            
        Returns:
            str: JSON string containing the evaluation result
            
        Raises:
            WavesInvalidResponse: If the API returns an error or request fails
        """
        CONTRACT_ADDRESS = "3P2mUshsGaj2B5A9rSD4wwXk47fHB16Sidk"
        log_debug(f"Evaluating expression '{expr}' on contract {CONTRACT_ADDRESS}")
        
        try:
            url = f"{self.node}/utils/script/evaluate/{CONTRACT_ADDRESS}"
            payload = {"expr": expr}
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            if "error" in result:
                raise WavesInvalidResponse(f"API returned error: {result['error']}")
                
            return json.dumps(result, indent=2)
            
        except requests.RequestException as e:
            logger.error(f"Network error evaluating smart contract: {e}")
            raise WavesInvalidResponse(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            raise WavesInvalidResponse(f"Invalid response format: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error evaluating smart contract: {e}")
            raise WavesInvalidResponse(f"Unexpected error: {str(e)}")

    def get_puzzle_lend_markets(self) -> List[dict]:
        """
        Get all Puzzle Lend markets information by calling getMarketJson function.
        
        Returns:
            List[dict]: List of dictionaries containing all markets data
        """
        log_debug(f"Fetching Puzzle Lend markets")
        try:
            pools_information = []
            for i in range(5):
                result = self.evaluate_smart_contract(
                    f"getMarketJson({i}, \"\", false)"
                )
                result_json = json.loads(result)
                
                # Validate response structure
                if not isinstance(result_json, dict) or 'result' not in result_json:
                    logger.error(f"Invalid response format for market {i}")
                    continue
                    
                pool_value = result_json['result'].get('value')
                if not pool_value:
                    logger.error(f"No value field in response for market {i}")
                    continue
                    
                try:
                    pool_data = json.loads(pool_value)
                    if isinstance(pool_data, dict) and not "error" in pool_data:
                        pools_information.append(pool_data)
                    else:
                        logger.warning(f"Invalid pool data format for market {i}")
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse pool data for market {i}")
                    continue
                    
            if not pools_information:
                return json.dumps({"error": "No valid markets found"})
                
            return pools_information
            
        except Exception as e:
            logger.error(f"Error fetching Puzzle Lend markets: {e}")
            return json.dumps({"error": str(e)})

    def get_puzzle_lend_usdt_pools(self) -> str:
        """
        Get information about USDT assets across all Puzzle Lend pools.
        Filters the full markets data to return only USDT asset information.
        
        Returns:
            List[dict]: List of dictionaries containing USDT asset information from each pool. 
            Each dictionary contains:
                - market_index: Index of the market
                - market_name: Name of the market
                - market_address: Address of the market
                - market_active: Whether the market is active
                - market_supply_apy: Supply APY of the market. The value is in the format where 1 equals 1% (e.g. 5.5 means 5.5%)
                - asset_id: Asset ID
                - asset_name: Asset name
                - asset_supply: Supply of the asset
        """
        log_debug("Fetching USDT assets from Puzzle Lend pools")
        try:
            markets = self.get_puzzle_lend_markets()
            
            if isinstance(markets, str) and "error" in markets:
                return markets
                
            usdt_assets = []
            for market in markets:
                # Look through each asset in the market
                for asset in market.get("assets", []):
                    # Check if this is a USDT asset and not the old USDT asset
                    if asset.get("supply", {}).get("name", "").startswith("USDT") \
                        and asset["supply"]["id"] != '34N9YcEETLWn93qYQ64EsP1x89tSruJU44RrEMSXXEPJ':

                        asset_info = {
                            "market_index": market.get("index", ""),
                            "market_name": market.get("name", ""),
                            "market_address": market.get("address", ""),
                            "market_active": market.get("active", False),
                            "market_supply_apy": asset["supplyApy"]["quantity"]/10**(asset["supplyApy"]["decimals"] - 2),
                            # "market_borrow_apy": asset["borrowApy"]["quantity"]/10**(asset["borrowApy"]["decimals"]),
                            # "market_utilization_ratio": asset["utilizationRatio"]["quantity"]/10**(asset["utilizationRatio"]["decimals"]),
                            "asset_id": asset["supply"]["id"],
                            "asset_name": asset["supply"]["name"],
                            "asset_supply": asset["supply"]["quantity"]/10**(asset["supply"]["decimals"]),
                            # "asset_supply_in_usd": asset["supplyInUsd"]["quantity"]/10**(asset["supplyInUsd"]["decimals"]),
                            # "asset_borrow": asset["borrow"]["quantity"]/10**(asset["borrow"]["decimals"])
                        }
                        usdt_assets.append(asset_info)
            
            return json.dumps(usdt_assets, indent=2)
        except Exception as e:
            logger.error(f"Error filtering USDT assets: {e}")
            return json.dumps({"error": str(e)})
    
    def get_puzzle_lend_wallet_supply(self, address: Optional[str] = None) -> str:
        """
        Get the supply of all assets in the wallet.
        If address is not provided, uses the initialized address.
            
        Returns:
            List[dict]: List of dictionaries containing asset information
            Each dictionary contains:
                - market_name: Name of the market
                - market_address: Address of the market
                - market_active: Whether the market is active
                - asset_id: Asset ID
                - asset_name: Asset name
                - wallet_supply: Supply of the asset in the wallet
                - wallet_supply_in_usd: Supply of the asset in the wallet in USD
        """
        try:
            usdt_pools = json.loads(self.get_puzzle_lend_usdt_pools())
            address = self.address.address if not address else address
            wallet_supply = []
            for pool in usdt_pools:
                try:
                    pool_stats_wallet = self.evaluate_smart_contract(
                        f"getWalletOperationsJson({pool['market_index']}, \"{pool['asset_id']}\", \"{address}\", false)"
                    )
                    pool_stats_wallet_json = json.loads(json.loads(pool_stats_wallet)['result']['value'])
                    wallet_supply.append({
                        "market_name": pool['market_name'],
                        "market_address": pool['market_address'],
                        "market_active": pool['market_active'],
                        "asset_id": pool['asset_id'],
                        "asset_name": pool['asset_name'],
                        "wallet_supply": pool_stats_wallet_json["walletSupply"]["quantity"]/10**(pool_stats_wallet_json["walletSupply"]["decimals"]),
                        "wallet_supply_in_usd": pool_stats_wallet_json["walletSupplyInUsd"]["quantity"]/10**(pool_stats_wallet_json["walletSupplyInUsd"]["decimals"]),
                    })
                except WavesInvalidResponse as e:
                    logger.error(f"Error fetching wallet supply for {pool['asset_id']}: {e}")
                    continue

            return json.dumps(wallet_supply, indent=2)
        except Exception as e:
            logger.error(f"Error fetching wallet supply: {e}")
            return json.dumps({"error": str(e)})

    def get_wallet_assets(self, address: Optional[str] = None) -> List[dict]:
        """
        Get the balance of all assets in the wallet. 
        If address is not provided, uses the initialized address.

        Returns:
            List[dict]: List of dictionaries containing asset information
            Each dictionary contains:
                - asset_id: Asset ID
                - asset_name: Asset name
                - balance: Balance of the asset
        """
        try:
            if not address:
                address = self.address
            else:
                address = pw.Address(address=address)

            wallet_assets = []
            for asset in address.assets():
                asset = pw.Asset(asset)
                asset_info = {
                    "asset_id": asset.assetId,
                    "asset_name": asset.name,
                    "balance": address.balance(asset.assetId) / 10**asset.decimals
                }
                wallet_assets.append(asset_info)

            return wallet_assets
        except Exception as e:
            logger.error(f"Error fetching wallet assets: {e}")
            return []

    def get_wallet_waves_balance(self, address: Optional[str] = None) -> float:
        """
        Get the WAVES balance for an address.
        If address is not provided, uses the initialized address.
        
        Args:
            address (Optional[str]): The address to check balance for. 
                                    If None, uses the initialized address.
            
        Returns:
            str: JSON string containing WAVES balance information
        """
        try:
            if not address:
                address = self.address
            else:
                address = pw.Address(address=address)
            
            balance = address.balance() / 10**8
            log_debug(f"Fetching WAVES balance for {address.address}")
            return balance
        
        except Exception as e:
            logger.error(f"Error fetching WAVES balance: {e}")
            return 0

    def get_wallet_token_balance(self, asset_id: str, address: Optional[str] = None) -> float:
        """
        Get the balance of a specific token for an address.
        If address is not provided, uses the initialized address.   
        
        Args:
            asset_id (str): The asset ID of the token
            address (Optional[str]): The address to check balance for.
                                     If None, uses the initialized address.
            
        Returns:
            float: Token balance in the specified asset
        """
        try:
            if not address:
                address = self.address
            else:
                address = pw.Address(address=address)

            if asset_id.lower() == "waves":
                return address.balance() / 10**8
            else:
                asset = pw.Asset(asset_id)
                return address.balance(asset.assetId) / 10**asset.decimals
        except Exception as e:
            logger.error(f"Error fetching token balance: {e}")
            return 0

    def get_wallet_usdt_balance(self, address: Optional[str] = None) -> str:
        """
        Get the balance of USDT for an address. There are multiple USDT assets in the Puzzle Lend pools.
        If address is not provided, uses the initialized address.

        Returns:
            List[dict]: List of dictionaries containing USDT balance information
            Each dictionary contains:   
                - asset_id: Asset ID
                - asset_name: Asset name
                - balance: Balance of the asset
        """
        try:
            usdt_tokens = set()  # Use a set to store unique token identifiers
            puzzle_usdt_pools = json.loads(self.get_puzzle_lend_usdt_pools())
            
            # Create unique token identifiers using tuples (which are hashable)
            for pool in puzzle_usdt_pools:
                token_key = (pool['asset_id'], pool['asset_name'])
                usdt_tokens.add(token_key)
            
            address = self.address.address if not address else address
            wallet_usdt_balance = []
            
            # Iterate over unique tokens and get balances
            for asset_id, asset_name in usdt_tokens:
                balance = self.get_wallet_token_balance(asset_id, address)
                wallet_usdt_balance.append({
                    "asset_id": asset_id,
                    "asset_name": asset_name,
                    "balance": balance
                })
            
            return json.dumps(wallet_usdt_balance, indent=2)
        except Exception as e:
            logger.error(f"Error fetching USDT balance: {e}")
            return json.dumps({"error": str(e)})

    def invoke_script(
        self, 
        dapp_address: str,
        function_name: str,
        params: List[dict] = None,
        payments: List[dict] = None,
        fee_asset: str = None,
        tx_fee: int = None,
        description: str = ""
    ) -> str:
        """
        Invoke a script function on a dApp smart contract.
        
        Args:
            dapp_address (str): The address of the dApp to invoke
            function_name (str): The name of the function to call
            params (List[dict], optional): List of parameters to pass to the function.
                Each parameter is a dict with 'type' and 'value' keys.
                Example: [{'type': 'integer', 'value': 123}, {'type': 'string', 'value': 'hello'}]
            payments (List[dict], optional): List of payments to include with the invocation.
                Each payment is a dict with 'assetId' and 'amount' keys.
                Example: [{'assetId': 'WAVES', 'amount': 1000000}, {'assetId': 'asset_id_here', 'amount': 5000}]
            fee_asset (str, optional): The asset ID to pay the fee in. None for WAVES.
            tx_fee (int, optional): The fee amount. If None, uses the default fee.
            description (str, optional): A description of what this invocation does (for logging)
            
        Returns:
            str: JSON string containing transaction result
            
        Raises:
            WavesException: If no private key is available or other validation fails
            WavesInvalidAddress: If the dApp address is invalid
        """
        log_debug(f"Invoking {function_name} on dApp {dapp_address}" + 
                  (f" ({description})" if description else ""))
        
        try:
            if not self.address or not self.address.privateKey:
                raise WavesException("Private key not available for transaction signing")
                
            # Default empty lists if None
            params = params or []
            payments = payments or []
            
            # Use default fee if not specified
            if tx_fee is None:
                tx_fee = pw.DEFAULT_INVOKE_SCRIPT_FEE
                
            # Convert payment amounts to integers if they're WAVES (8 decimals) or 
            # determine decimals based on asset ID for other assets
            processed_payments = []
            for payment in payments:
                asset_id = payment.get('assetId')
                amount = payment.get('amount')
                
                if asset_id == 'WAVES' or asset_id is None:
                    if isinstance(amount, float):
                        amount = int(amount * 10**8)  # Convert WAVES to wavelets
                else:
                    # For other assets, we need to determine decimals
                    try:
                        asset = pw.Asset(asset_id)
                        if isinstance(amount, float):
                            amount = int(amount * 10**asset.decimals)
                    except Exception as e:
                        raise WavesInvalidAsset(f"Failed to process payment asset {asset_id}: {str(e)}")
                
                processed_payments.append({
                    'assetId': asset_id,
                    'amount': amount
                })
                
            # Make the actual invocation call
            tx = self.address.invokeScript(
                dappAddress=dapp_address,
                functionName=function_name,
                params=params,
                payments=processed_payments,
                feeAsset=fee_asset,
                txFee=tx_fee
            )
            
            # Process the result
            tx_info = {
                "success": "error" not in tx,
                "transaction_id": tx.get("id", "Unknown"),
                "from_address": self.address.address,
                "dapp_address": dapp_address,
                "function": function_name,
                "params": params,
                "payments": payments,
                "fee": tx_fee / (10**8),  # Convert to WAVES
                "fee_asset": fee_asset or "WAVES",
                "timestamp": tx.get("timestamp", 0)
            }
            
            if "error" in tx:
                tx_info["error"] = tx["error"]
                logger.error(f"Transaction error: {tx['error']}")
            else:
                logger.info(f"Transaction {tx.get('id', 'Unknown')} successful")
            return tx_info
        
        except WavesException:
            # Re-raise known exceptions
            raise
        except Exception as e:
            logger.error(f"Error invoking script: {e}")
            raise WavesException(f"Failed to invoke script: {str(e)}")

    def puzzle_lend_supply_assets(
        self,
        payment_amount: float,
        payment_asset_id: str,
        pool_address: str
    ) -> str:
        """
        Supply assets in a Puzzle Lend liquidity pool.
        
        This method:
        1. Verifies that sufficient balance is available
        2. Supplies the specified amount to the Puzzle pool
        
        Args:
            payment_amount (float): Amount to supply in human-readable form (e.g., 10.5 USDT)
            payment_asset_id (str): Asset ID of the token to supply (use 'WAVES' for WAVES)
            pool_address (str): The address of the Puzzle pool (dApp address)
        Returns:
            str: JSON string containing transaction result
            
        Raises:
            WavesException: If balance is insufficient or other errors occur
            WavesInvalidAddress: If pool address is invalid
            WavesInvalidAsset: If asset ID is invalid
        """
        log_debug(f"Supplying {payment_amount} of {payment_asset_id} in Puzzle pool: {pool_address}")
        
        try:
            # Check if private key is available
            if not self.address or not self.address.privateKey:
                raise WavesException("Private key not available for transaction signing")

            # Check user's balance first
            user_balance = self.get_wallet_token_balance(payment_asset_id)
            
            # We need to know the transaction fee to ensure sufficient balance
            tx_fee = pw.DEFAULT_INVOKE_SCRIPT_FEE
            tx_fee_in_waves = tx_fee / (10**8)
            
            # If token is WAVES, ensure balance covers both stake amount and fee
            if payment_asset_id.lower() == 'waves':
                if user_balance < payment_amount + tx_fee_in_waves:
                    raise WavesException(
                        f"Insufficient WAVES balance. Required: {payment_amount + tx_fee_in_waves} WAVES, Available: {user_balance} WAVES"
                    )
            else:
                # For other tokens, check token balance and WAVES balance for fee separately
                if user_balance < payment_amount:
                    raise WavesException(
                        f"Insufficient {payment_asset_id} balance. Required: {payment_amount}, Available: {user_balance}"
                    )
                
                # Also check if there's enough WAVES for the fee
                waves_balance = self.get_wallet_waves_balance()
                if waves_balance < tx_fee_in_waves:
                    raise WavesException(
                        f"Insufficient WAVES balance for transaction fee. Required: {tx_fee_in_waves} WAVES, Available: {waves_balance} WAVES"
                    )
            
            # Prepare payment for the stake
            payments = [{
                "assetId": payment_asset_id,
                "amount": int(math.floor(payment_amount) * 10**(pw.Asset(payment_asset_id).decimals))
            }]

            # Execute the stake transaction using invoke_script
            result = self.invoke_script(
                dapp_address=pool_address,
                function_name="supply",
                payments=payments,
                description=f"Supplying {payment_amount} {payment_asset_id} in Puzzle pool"
            )
            
            # Add some additional context to the result
            result["operation"] = "supply"
            result["pool_address"] = pool_address
            result["supplied_amount"] = payment_amount
            result["supplied_asset"] = payment_asset_id
            
            return json.dumps(result, indent=2)
            
        except WavesException:
            # Re-raise known exceptions
            raise
        except Exception as e:
            logger.error(f"Error staking in Puzzle pool: {e}")
            raise WavesException(f"Failed to stake in Puzzle pool: {str(e)}")

    def puzzle_lend_withdraw_assets(
        self,
        withdraw_amount: float,
        asset_id: str,
        pool_address: str
    ) -> str:
        """
        Withdraw assets from a Puzzle Lend liquidity pool.
        
        This method:
        1. Verifies that sufficient WAVES balance is available for transaction fee
        2. Checks that user has enough supplied balance to withdraw
        3. Withdraws the specified amount from the Puzzle pool
        
        Args:
            withdraw_amount (float): Amount to withdraw in human-readable form (e.g., 10.5 USDT)
            asset_id (str): Asset ID of the token to withdraw (use 'WAVES' for WAVES)
            pool_address (str): The address of the Puzzle pool (dApp address)
            
        Returns:
            str: JSON string containing transaction result
            
        Raises:
            WavesException: If balance is insufficient or other errors occur
            WavesInvalidAddress: If pool address is invalid
            WavesInvalidAsset: If asset ID is invalid
        """
        log_debug(f"Withdrawing {withdraw_amount} of {asset_id} from Puzzle pool {pool_address}")
        
        try:
            # Check if private key is available
            if not self.address or not self.address.privateKey:
                raise WavesException("Private key not available for transaction signing")

            # 1. Check if user has enough WAVES for transaction fee
            tx_fee = pw.DEFAULT_INVOKE_SCRIPT_FEE
            tx_fee_in_waves = tx_fee / (10**8)
            
            waves_balance = self.get_wallet_waves_balance()
            if waves_balance < tx_fee_in_waves:
                raise WavesException(
                    f"Insufficient WAVES balance for transaction fee. Required: {tx_fee_in_waves} WAVES, Available: {waves_balance} WAVES"
                )
            
            # 2. Check if user has sufficient supplied balance to withdraw
            supplied_amounts = json.loads(self.get_puzzle_lend_wallet_supply())
            
            # Find the specific pool and asset combination
            user_supplied_amount = 0
            found_asset = False
            
            for supplied_asset in supplied_amounts:
                if supplied_asset["market_address"] == pool_address and supplied_asset["asset_id"] == asset_id:
                    user_supplied_amount = supplied_asset["wallet_supply"]
                    found_asset = True
                    break
                    
            if not found_asset:
                raise WavesException(f"No supplied assets found for {asset_id} in pool {pool_address}")
            
            if user_supplied_amount < withdraw_amount:
                raise WavesException(
                    f"Insufficient supplied balance. Requested to withdraw: {withdraw_amount}, Available: {user_supplied_amount}"
                )
            
            # 3. Prepare parameters for withdraw function
            # The withdraw function requires the asset ID and amount as parameters
            params = [
                {"type": "string", "value": asset_id},
                {
                    "type": "integer", 
                    "value": int(math.floor(withdraw_amount) * 10**(pw.Asset(asset_id).decimals))
                }
            ]
            
            # 4. Execute the withdraw transaction
            result = self.invoke_script(
                dapp_address=pool_address,
                function_name="withdraw",
                params=params,            # The withdraw function takes parameters instead of payments
                payments=[],              # No payments for withdrawal
                description=f"Withdrawing {withdraw_amount} {asset_id} from Puzzle pool"
            )
            
            # 5. Add additional context to the result
            result["operation"] = "withdraw"
            result["pool_address"] = pool_address
            result["withdrawn_amount"] = withdraw_amount
            result["withdrawn_asset"] = asset_id
            
            return json.dumps(result, indent=2)
            
        except WavesException:
            # Re-raise known exceptions
            raise
        except Exception as e:
            logger.error(f"Error withdrawing from Puzzle pool: {e}")
            raise WavesException(f"Failed to withdraw from Puzzle pool: {str(e)}")

    # Helper method to get asset ID by token name.
    @staticmethod
    def get_asset_id_by_name(token_name: str) -> Optional[str]:
        """
        Helper method to get asset ID by token name.
        
        Args:
            token_name (str): Name of the token (e.g., "USDT-ERC20", "WAVES")
            
        Returns:
            Optional[str]: Asset ID if found, None otherwise
        """
        # Special case for WAVES
        if token_name.upper() == "WAVES":
            return "WAVES"
        
        # Search through TOKENS dictionary
        for asset_id, token_info in TOKENS.items():
            if token_info["name"].upper() == token_name.upper() or \
               token_info["name"].upper().startswith(token_name.upper()):
                return asset_id
        return None

    def puzzle_swap_tokens(
        self,
        input_amount: float,
        input_token: str,
        output_token: str,
        slippage_percent: float = 0.5
    ) -> str:
        """
        Swap tokens using the Puzzle Swap aggregator.
        
        This method:
        1. Resolves token names to asset IDs if needed
        2. Calls the Puzzle Swap API to calculate the optimal swap route
        3. Verifies that sufficient balance is available
        4. Executes the swap transaction through the Puzzle Swap aggregator
        
        Args:
            input_amount (float): Amount to swap in human-readable form (e.g., 10.5 USDT)
            input_token (str): Asset ID or name of the token to swap from (e.g., "USDT-ERC20" or asset ID)
            output_token (str): Asset ID or name of the token to swap to (e.g., "WAVES" or asset ID)
            slippage_percent (float): Maximum acceptable slippage percentage (default 0.5%)
            
        Returns:
            str: JSON string containing transaction result
            
        Raises:
            WavesException: If balance is insufficient or other errors occur
        """
        log_debug(f"Preparing to swap {input_amount} of {input_token} for {output_token}")
        
        try:
            # Resolve input token
            input_asset_id = input_token
            if len(input_token) < 15:
                log_debug(f"Resolving input token name: {input_token}")
                resolved_input = self.get_asset_id_by_name(input_token)
                if not resolved_input:
                    raise WavesException(f"Could not resolve input token name: {input_token}")
                input_asset_id = resolved_input
            
            # Resolve output token
            output_asset_id = output_token
            if len(output_token) < 15:
                log_debug(f"Resolving output token name: {output_token}")
                resolved_output = self.get_asset_id_by_name(output_token)
                if not resolved_output:
                    raise WavesException(f"Could not resolve output token name: {output_token}")
                output_asset_id = resolved_output
            
            log_debug(f"Resolved asset IDs - Input: {input_asset_id}, Output: {output_asset_id}")

            # Check if private key is available
            if not self.address or not self.address.privateKey:
                raise WavesException("Private key not available for transaction signing")

            # Convert human-readable amount to asset's smallest unit
            asset_decimals = 8 if input_asset_id.lower() == 'waves' else pw.Asset(input_asset_id).decimals
            amount_in_smallest_unit = int(input_amount * 10**asset_decimals)
            
            # Check user's balance
            user_balance = self.get_wallet_token_balance(input_asset_id)
            if user_balance < input_amount:
                raise WavesException(
                    f"Insufficient {input_token} balance. Required: {input_amount}, Available: {user_balance}"
                )
            
            # Check if there's enough WAVES for the fee
            tx_fee = pw.DEFAULT_INVOKE_SCRIPT_FEE
            tx_fee_in_waves = tx_fee / (10**8)
            waves_balance = self.get_wallet_waves_balance()
            if waves_balance < tx_fee_in_waves:
                raise WavesException(
                    f"Insufficient WAVES balance for transaction fee. Required: {tx_fee_in_waves} WAVES, Available: {waves_balance} WAVES"
                )
            
            # Call Puzzle Swap API to get swap parameters
            swap_url = f"https://swapapi.puzzleswap.org/aggregator/calc?token0={input_asset_id}&token1={output_asset_id}&amountIn={amount_in_smallest_unit}"
            log_debug(f"Calling Puzzle Swap API: {swap_url}")
            
            try:
                response = requests.get(swap_url, timeout=30)
                response.raise_for_status()
                swap_data = response.json()
                
                if "error" in swap_data and swap_data["error"]:
                    raise WavesException(f"Puzzle Swap API error: {swap_data['error']}")
                    
                if "parameters" not in swap_data or not swap_data["parameters"]:
                    raise WavesException("Missing swap parameters in API response")
                    
                # Get the route parameters and estimated output
                route_parameters = swap_data["parameters"]
                estimated_out = swap_data.get("estimatedOut", 0)
                
                # Apply slippage tolerance to the minimum output amount
                min_output_amount = int(estimated_out * (1 - slippage_percent/100))
                
                # Prepare parameters for the swap function call
                params = [
                    {"type": "string", "value": route_parameters},
                    {"type": "integer", "value": min_output_amount}
                ]
                
                # Create payment for the swap
                payments = [{
                    "assetId": input_asset_id if input_asset_id.lower() != 'waves' else None,
                    "amount": amount_in_smallest_unit
                }]
                
                # Execute the swap transaction
                result = self.invoke_script(
                    dapp_address="3PGFHzVGT4NTigwCKP1NcwoXkodVZwvBuuU",
                    function_name="swap",
                    params=params,
                    payments=payments,
                    description=f"Swapping {input_amount} {input_token} for {output_token}"
                )
                
                # Add additional context to the result
                result["operation"] = "swap"
                result["input_amount"] = input_amount
                result["input_token"] = input_token
                result["input_asset_id"] = input_asset_id
                result["output_token"] = output_token
                result["output_asset_id"] = output_asset_id
                result["estimated_output"] = estimated_out / (10**(8 if output_asset_id.lower() == 'waves' else pw.Asset(output_asset_id).decimals))
                result["price_impact"] = swap_data.get("priceImpact", 0) * 100  # Convert to percentage
                
                return json.dumps(result, indent=2)
                
            except requests.RequestException as e:
                logger.error(f"Network error calling Puzzle Swap API: {e}")
                raise WavesException(f"Network error: {str(e)}")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from Puzzle Swap API: {e}")
                raise WavesException(f"Invalid API response format: {str(e)}")
                
        except WavesException:
            # Re-raise known exceptions
            raise
        except Exception as e:
            logger.error(f"Error swapping tokens: {e}")
            raise WavesException(f"Failed to swap tokens: {str(e)}")
