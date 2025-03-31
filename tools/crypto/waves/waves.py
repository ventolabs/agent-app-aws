import json
from typing import Optional

import pywaves as pw
from agno.tools import Toolkit
from agno.utils.functions import cache_result
from agno.utils.log import log_debug, logger

try:
    import requests
except ImportError:
    raise ImportError("`requests` not installed. Please install using `pip install requests`.")


class WavesTools(Toolkit):
    """
    WavesTools is a toolkit for interacting with the Waves blockchain.
    
    This toolkit provides functionality to:
    1. Query Puzzle Lend smart contracts
    2. Get pool information and APY rates
    3. Execute transactions on the Waves blockchain
    4. Manage liquidity positions
    
    Args:
        node (str): Waves node URL
        chain (str): Chain to use (mainnet/testnet)
        puzzle_lend_address (str): Address of the Puzzle Lend smart contract
        private_key (Optional[str]): Private key for transaction signing
        cache_results (bool): Enable caching for read operations
        cache_ttl (int): Cache time-to-live in seconds
        cache_dir (Optional[str]): Directory to store cache files
    """

    def __init__(
        self,
        node: str = "https://nodes.wavesnodes.com",
        chain: str = "mainnet",
        private_key: Optional[str] = None,
        address: Optional[str] = None,
        cache_results: bool = True,
        cache_ttl: int = 300,  # 5 minutes
        cache_dir: Optional[str] = None,
    ):
        super().__init__(name="waves")

        # Initialize PyWaves configuration
        pw.setNode(node=node, chain=chain)
            
        # Set up wallet if private key is provided
        self.address = None
        if private_key:
            self.address = pw.Address(privateKey=private_key)
        elif address:
            self.address = pw.Address(address=address)
            
        self.node = node
        self.chain = chain
        self.cache_results = cache_results
        self.cache_ttl = cache_ttl
        self.cache_dir = cache_dir

        # Register functions
        self.register(self.get_puzzle_lend_markets)
        self.register(self.get_pool_apy)
        self.register(self.get_usdt_pools)
        self.register(self.get_wave_balance)
        self.register(self.get_token_balance)
        self.register(self.transfer_token)
        self.register(self.stake_in_pool)
        self.register(self.unstake_from_pool)
        self.register(self.evaluate_smart_contract)

    @cache_result()
    def evaluate_smart_contract(self, expr: str) -> str:
        """
        Evaluate an expression on a smart contract using Waves node API.
        
        Args:
            expr (str): The expression to evaluate
            
        Returns:
            str: JSON string containing the evaluation result
        """
        log_debug(f"Evaluating expression '{expr}' on contract 3P2mUshsGaj2B5A9rSD4wwXk47fHB16Sidk")
        try:
            url = f"{self.node}/utils/script/evaluate/3P2mUshsGaj2B5A9rSD4wwXk47fHB16Sidk"
            payload = {"expr": expr}
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            return json.dumps(response.json(), indent=2)
        except Exception as e:
            logger.error(f"Error evaluating smart contract: {e}")
            return json.dumps({"error": str(e)})

    @cache_result()
    def get_puzzle_lend_markets(self) -> str:
        """
        Get all Puzzle Lend markets information by calling getMarketJson function.
        
        Returns:
            str: JSON string containing all markets data
        """
        log_debug(f"Fetching Puzzle Lend markets")
        try:
            result = self.evaluate_smart_contract(
                "getMarketJson(0, \"\", false)"
            )
            return result
        except Exception as e:
            logger.error(f"Error fetching Puzzle Lend markets: {e}")
            return json.dumps({"error": str(e)})

    @cache_result()
    def get_usdt_pools(self) -> str:
        """
        Get information about USDT liquidity pools on Puzzle Lend.
        Filters the full markets data to return only USDT pools.
        
        Returns:
            str: JSON string containing USDT pool information
        """
        log_debug("Fetching USDT pools from Puzzle Lend")
        try:
            markets_json = self.get_puzzle_lend_markets()
            markets = json.loads(markets_json)
            
            if "error" in markets:
                return markets_json
                
            usdt_pools = []
            for market in markets.get("result", {}).get("value", []):
                # Check if this is a USDT pool
                if "USDT" in market.get("name", ""):
                    usdt_pools.append(market)
            
            return json.dumps({"usdt_pools": usdt_pools}, indent=2)
        except Exception as e:
            logger.error(f"Error filtering USDT pools: {e}")
            return json.dumps({"error": str(e)})
    
    @cache_result()
    def get_pool_apy(self, pool_id: str) -> str:
        """
        Get the current APY for a specific pool.
        
        Args:
            pool_id (str): The ID of the pool
            
        Returns:
            str: JSON string containing pool APY information
        """
        log_debug(f"Fetching APY for pool {pool_id}")
        try:
            markets_json = self.get_puzzle_lend_markets()
            markets = json.loads(markets_json)
            
            if "error" in markets:
                return markets_json
                
            for market in markets.get("result", {}).get("value", []):
                if market.get("poolId") == pool_id:
                    apy_info = {
                        "pool_id": pool_id,
                        "name": market.get("name", "Unknown"),
                        "current_apy": market.get("depositAPY", 0),
                        "total_deposited": market.get("totalDeposit", 0),
                        "utilization_rate": market.get("utilizationRate", 0)
                    }
                    return json.dumps(apy_info, indent=2)
            
            return json.dumps({"error": f"Pool {pool_id} not found"})
        except Exception as e:
            logger.error(f"Error fetching pool APY: {e}")
            return json.dumps({"error": str(e)})

    def get_waves_balance(self, address: Optional[str] = None) -> str:
        """
        Get the WAVES balance for an address.
        
        Args:
            address (Optional[str]): The address to check balance for. 
                                    If None, uses the initialized address.
            
        Returns:
            str: JSON string containing WAVES balance information
        """
        try:
            target_address = address if address else (self.address.address if self.address else None)
            
            if not target_address:
                return json.dumps({"error": "No address specified"})
                
            log_debug(f"Fetching WAVES balance for {target_address}")
            addr = pw.Address(address=target_address)
            
            balance_info = {
                "address": target_address,
                "waves_balance": addr.balance(),
                "formatted_balance": f"{addr.balance() / 10**8:.8f} WAVES"
            }
            return json.dumps(balance_info, indent=2)
        except Exception as e:
            logger.error(f"Error fetching WAVES balance: {e}")
            return json.dumps({"error": str(e)})

    def get_token_balance(self, asset_id: str, address: Optional[str] = None) -> str:
        """
        Get the balance of a specific token for an address.
        
        Args:
            asset_id (str): The asset ID of the token
            address (Optional[str]): The address to check balance for.
                                     If None, uses the initialized address.
            
        Returns:
            str: JSON string containing token balance information
        """
        try:
            target_address = address if address else (self.address.address if self.address else None)
            
            if not target_address:
                return json.dumps({"error": "No address specified"})
                
            log_debug(f"Fetching token {asset_id} balance for {target_address}")
            addr = pw.Address(address=target_address)
            asset = pw.Asset(asset_id)
            
            balance = addr.balance(assetId=asset_id)
            decimals = asset.decimals
            
            balance_info = {
                "address": target_address,
                "asset_id": asset_id,
                "asset_name": asset.name,
                "balance": balance,
                "formatted_balance": f"{balance / 10**decimals:.{decimals}f} {asset.name}"
            }
            return json.dumps(balance_info, indent=2)
        except Exception as e:
            logger.error(f"Error fetching token balance: {e}")
            return json.dumps({"error": str(e)})

    def transfer_token(
        self, 
        recipient: str, 
        asset_id: str, 
        amount: float, 
        fee: int = 100000,
        attachment: str = ""
    ) -> str:
        """
        Transfer tokens to another address.
        
        Args:
            recipient (str): Recipient address
            asset_id (str): Asset ID of the token to transfer (use 'WAVES' for WAVES)
            amount (float): Amount to transfer (in token units, not satoshis)
            fee (int): Transaction fee in WAVES satoshis (default: 100000 = 0.001 WAVES)
            attachment (str): Optional attachment/memo for the transaction
            
        Returns:
            str: JSON string containing transaction result
        """
        log_debug(f"Transferring {amount} of {asset_id} to {recipient}")
        try:
            if not self.address or not self.address.privateKey:
                return json.dumps({"error": "Private key not available for transaction signing"})
                
            # Handle WAVES transfer differently
            if asset_id.upper() == "WAVES":
                amount_in_satoshi = int(amount * 10**8)
                tx = self.address.sendWaves(recipient=pw.Address(recipient), 
                                          amount=amount_in_satoshi, 
                                          txFee=fee,
                                          attachment=attachment)
            else:
                # Get decimals for the asset
                asset = pw.Asset(asset_id)
                decimals = asset.decimals
                amount_in_satoshi = int(amount * 10**decimals)
                
                tx = self.address.sendAsset(recipient=pw.Address(recipient),
                                          assetId=asset_id,
                                          amount=amount_in_satoshi,
                                          txFee=fee,
                                          attachment=attachment)
            
            tx_info = {
                "transaction_id": tx.get("id", "Unknown"),
                "from_address": self.address.address,
                "to_address": recipient,
                "asset": asset_id if asset_id.upper() != "WAVES" else "WAVES",
                "amount": amount,
                "fee": fee / 10**8,
                "timestamp": tx.get("timestamp", 0),
                "status": "Success" if "error" not in tx else "Failed",
            }
            
            if "error" in tx:
                tx_info["error"] = tx["error"]
                
            return json.dumps(tx_info, indent=2)
        except Exception as e:
            logger.error(f"Error transferring tokens: {e}")
            return json.dumps({"error": str(e)})

    def stake_in_pool(self, pool_id: str, amount: float) -> str:
        """
        Stake tokens in a Puzzle Lend liquidity pool.
        This is a simplified implementation - in production you would need to interact
        with the specific pool's smart contract functions.
        
        Args:
            pool_id (str): The ID of the pool to stake in
            amount (float): Amount to stake (in token units)
            
        Returns:
            str: JSON string containing staking transaction result
        """
        log_debug(f"Staking {amount} in pool {pool_id}")
        try:
            if not self.address or not self.address.privateKey:
                return json.dumps({"error": "Private key not available for transaction signing"})
            
            # Get pool information to determine the asset ID and contract address
            markets_json = self.get_puzzle_lend_markets()
            markets = json.loads(markets_json)
            
            pool_info = None
            for market in markets.get("result", {}).get("value", []):
                if market.get("poolId") == pool_id:
                    pool_info = market
                    break
                    
            if not pool_info:
                return json.dumps({"error": f"Pool {pool_id} not found"})
                
            asset_id = pool_info.get("assetId")
            if not asset_id:
                return json.dumps({"error": "Could not determine asset ID for pool"})
                
            # In a real implementation, this would call the specific smart contract function
            # for staking. For this example, we'll simulate it with a data transaction.
            
            # Create a dummy data transaction to represent staking
            # In production, this would be an invoke script transaction to the pool's contract
            data = [{
                "key": f"stake_pool_{pool_id}",
                "type": "string", 
                "value": f"Stake {amount} in pool {pool_id}"
            }]
            
            tx = self.address.dataTransaction(data=data, txFee=500000)
            
            stake_info = {
                "transaction_id": tx.get("id", "Unknown"),
                "address": self.address.address,
                "pool_id": pool_id,
                "asset_id": asset_id,
                "amount": amount,
                "timestamp": tx.get("timestamp", 0),
                "status": "Success (Simulated)" if "error" not in tx else "Failed",
                "note": "This is a simulated transaction. In production, specific smart contract calls would be used."
            }
            
            if "error" in tx:
                stake_info["error"] = tx["error"]
                
            return json.dumps(stake_info, indent=2)
        except Exception as e:
            logger.error(f"Error staking in pool: {e}")
            return json.dumps({"error": str(e)})

    def unstake_from_pool(self, pool_id: str, amount: float) -> str:
        """
        Unstake tokens from a Puzzle Lend liquidity pool.
        This is a simplified implementation - in production you would need to interact
        with the specific pool's smart contract functions.
        
        Args:
            pool_id (str): The ID of the pool to unstake from
            amount (float): Amount to unstake (in token units)
            
        Returns:
            str: JSON string containing unstaking transaction result
        """
        log_debug(f"Unstaking {amount} from pool {pool_id}")
        try:
            if not self.address or not self.address.privateKey:
                return json.dumps({"error": "Private key not available for transaction signing"})
            
            # Get pool information to determine the asset ID and contract address
            markets_json = self.get_puzzle_lend_markets()
            markets = json.loads(markets_json)
            
            pool_info = None
            for market in markets.get("result", {}).get("value", []):
                if market.get("poolId") == pool_id:
                    pool_info = market
                    break
                    
            if not pool_info:
                return json.dumps({"error": f"Pool {pool_id} not found"})
                
            asset_id = pool_info.get("assetId")
            if not asset_id:
                return json.dumps({"error": "Could not determine asset ID for pool"})
                
            # Create a dummy data transaction to represent unstaking
            # In production, this would be an invoke script transaction to the pool's contract
            data = [{
                "key": f"unstake_pool_{pool_id}",
                "type": "string", 
                "value": f"Unstake {amount} from pool {pool_id}"
            }]
            
            tx = self.address.dataTransaction(data=data, txFee=500000)
            
            unstake_info = {
                "transaction_id": tx.get("id", "Unknown"),
                "address": self.address.address,
                "pool_id": pool_id,
                "asset_id": asset_id,
                "amount": amount,
                "timestamp": tx.get("timestamp", 0),
                "status": "Success (Simulated)" if "error" not in tx else "Failed",
                "note": "This is a simulated transaction. In production, specific smart contract calls would be used."
            }
            
            if "error" in tx:
                unstake_info["error"] = tx["error"]
                
            return json.dumps(unstake_info, indent=2)
        except Exception as e:
            logger.error(f"Error unstaking from pool: {e}")
            return json.dumps({"error": str(e)})
