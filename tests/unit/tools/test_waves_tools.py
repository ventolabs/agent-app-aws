import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

# Adjust the import path based on your project structure
from tools.crypto.waves.waves import WavesTools
from tools.settings import settings
from tools.crypto.waves.exceptions import WavesException

# --- Mock Data ---

MOCK_NODE_URL = "https://nodes.wavesnodes.com"
MOCK_ADDRESS = "3P2mUshsGaj2B5A9rSD4wwXk47fHB16Sidk"
MOCK_ASSET_ID = "WAVES"
MOCK_POOL_ID_USDT = "PoolIDUSDT123"
MOCK_POOL_ID_OTHER = "PoolIDOther456"
MOCK_WAVES_PRIVATE_KEY = settings.waves.waves_mock_private_key

MOCK_EVALUATE_RESPONSE = {
    "result": {
        "value": [
            {
                "poolId": MOCK_POOL_ID_USDT,
                "name": "Puzzle USDT",
                "assetId": "34N9YcEETLWn93qYQ64EsP1x89tSruJU44RrEMSXXEPJ", # Example USDT Asset ID
                "depositAPY": 5.5,
                "totalDeposit": 1000000,
                "utilizationRate": 75.0,
            },
            {
                "poolId": MOCK_POOL_ID_OTHER,
                "name": "Puzzle WAVES",
                "assetId": "WAVES",
                "depositAPY": 3.2,
                "totalDeposit": 50000,
                "utilizationRate": 60.0,
            }
        ]
    }
}

MOCK_MARKETS_JSON = json.dumps(MOCK_EVALUATE_RESPONSE)

# --- Test Fixtures ---

@pytest.fixture
def waves_tools_no_key():
    """Provides a WavesTools instance without a private key."""
    return WavesTools(node=MOCK_NODE_URL, address=MOCK_ADDRESS, cache_results=False)

@pytest.fixture
def waves_tools_with_key():
    """Provides a WavesTools instance with a mock private key/address."""
    # We don't need a real private key for these tests, just mock the address object
    tools = WavesTools(node=MOCK_NODE_URL, private_key=MOCK_WAVES_PRIVATE_KEY, cache_results=False)
    # Manually override the address object created by pywaves with a mock
    tools.address = MagicMock()
    tools.address.address = MOCK_ADDRESS
    tools.address.privateKey = MOCK_WAVES_PRIVATE_KEY # Indicate a key is present
    return tools

# --- Test Functions ---

@patch('requests.post')
def test_evaluate_smart_contract_success(mock_post, waves_tools_no_key):
    """Test successful evaluation of a smart contract expression."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"result": "success"}
    mock_post.return_value = mock_response

    expr = "getSomething()"
    result_json = waves_tools_no_key.evaluate_smart_contract(expr)
    result = json.loads(result_json)

    mock_post.assert_called_once_with(
        f"{MOCK_NODE_URL}/utils/script/evaluate/3P2mUshsGaj2B5A9rSD4wwXk47fHB16Sidk",
        data=json.dumps({"expr": expr}),
        headers={"accept": "application/json", "Content-Type": "application/json"}
    )
    assert result == {"result": "success"}

@patch('requests.post')
def test_evaluate_smart_contract_error(mock_post, waves_tools_no_key):
    """Test error handling during smart contract evaluation."""
    mock_post.side_effect = Exception("Network Error")

    result_json = waves_tools_no_key.evaluate_smart_contract("getSomething()")
    result = json.loads(result_json)

    assert "error" in result
    assert "Network Error" in result["error"]

@patch('tools.crypto.waves.waves.WavesTools.evaluate_smart_contract')
def test_get_puzzle_lend_markets(mock_evaluate, waves_tools_no_key):
    """Test fetching all Puzzle Lend markets."""
    mock_evaluate.return_value = MOCK_MARKETS_JSON

    result_json = waves_tools_no_key.get_puzzle_lend_markets()
    result = json.loads(result_json)

    mock_evaluate.assert_called_once_with('getMarketJson(0, "", false)')
    assert result == MOCK_EVALUATE_RESPONSE

@patch('tools.crypto.waves.waves.WavesTools.get_puzzle_lend_markets')
def test_get_usdt_pools(mock_get_markets, waves_tools_no_key):
    """Test filtering for USDT pools."""
    mock_get_markets.return_value = MOCK_MARKETS_JSON

    result_json = waves_tools_no_key.get_usdt_pools()
    result = json.loads(result_json)

    mock_get_markets.assert_called_once()
    assert "usdt_pools" in result
    assert len(result["usdt_pools"]) == 1
    assert result["usdt_pools"][0]["poolId"] == MOCK_POOL_ID_USDT
    assert "USDT" in result["usdt_pools"][0]["name"]

@patch('tools.crypto.waves.waves.WavesTools.get_puzzle_lend_markets')
def test_get_pool_apy_found(mock_get_markets, waves_tools_no_key):
    """Test fetching APY for a specific existing pool."""
    mock_get_markets.return_value = MOCK_MARKETS_JSON

    result_json = waves_tools_no_key.get_pool_apy(MOCK_POOL_ID_USDT)
    result = json.loads(result_json)

    mock_get_markets.assert_called_once()
    assert result["pool_id"] == MOCK_POOL_ID_USDT
    assert result["name"] == "Puzzle USDT"
    assert result["current_apy"] == 5.5

@patch('tools.crypto.waves.waves.WavesTools.get_puzzle_lend_markets')
def test_get_pool_apy_not_found(mock_get_markets, waves_tools_no_key):
    """Test fetching APY for a non-existent pool."""
    mock_get_markets.return_value = MOCK_MARKETS_JSON

    result_json = waves_tools_no_key.get_pool_apy("NonExistentPoolID")
    result = json.loads(result_json)

    mock_get_markets.assert_called_once()
    assert "error" in result
    assert "not found" in result["error"]

@patch('pywaves.Address')
def test_get_waves_balance_initialized_address(mock_pw_address, waves_tools_with_key):
    """Test getting WAVES balance using the initialized address."""
    mock_addr_instance = MagicMock()
    mock_addr_instance.balance.return_value = 1234567890 # 12.3456789 WAVES
    mock_pw_address.return_value = mock_addr_instance

    result_json = waves_tools_with_key.get_waves_balance()
    result = json.loads(result_json)

    mock_pw_address.assert_called_once_with(address=MOCK_ADDRESS)
    mock_addr_instance.balance.assert_called_once()
    assert result["address"] == MOCK_ADDRESS
    assert result["waves_balance"] == 1234567890
    assert result["formatted_balance"] == "12.34567890 WAVES"

@patch('pywaves.Address')
def test_get_waves_balance_specific_address(mock_pw_address, waves_tools_no_key):
    """Test getting WAVES balance using a specifically provided address."""
    specific_address = "3PAnotherAddress0987654321fedcba"
    mock_addr_instance = MagicMock()
    mock_addr_instance.balance.return_value = 987650000 # 9.8765 WAVES
    mock_pw_address.return_value = mock_addr_instance

    result_json = waves_tools_no_key.get_waves_balance(address=specific_address)
    result = json.loads(result_json)

    mock_pw_address.assert_called_once_with(address=specific_address)
    mock_addr_instance.balance.assert_called_once()
    assert result["address"] == specific_address
    assert result["waves_balance"] == 987650000
    assert result["formatted_balance"] == "9.87650000 WAVES"

def test_get_waves_balance_no_address(waves_tools_no_key):
    """Test getting WAVES balance when no address is available."""
    # Ensure the instance truly has no address
    waves_tools_no_key.address = None
    result_json = waves_tools_no_key.get_waves_balance()
    result = json.loads(result_json)

    assert "error" in result
    assert "No address specified" in result["error"]


@patch('pywaves.Asset')
@patch('pywaves.Address')
def test_get_token_balance_initialized_address(mock_pw_address, mock_pw_asset, waves_tools_with_key):
    """Test getting token balance using the initialized address."""
    mock_addr_instance = MagicMock()
    mock_addr_instance.balance.return_value = 500000000 # 500 tokens if 6 decimals
    mock_pw_address.return_value = mock_addr_instance

    mock_asset_instance = MagicMock()
    type(mock_asset_instance).decimals = PropertyMock(return_value=6)
    type(mock_asset_instance).name = PropertyMock(return_value="MockToken")
    mock_pw_asset.return_value = mock_asset_instance

    result_json = waves_tools_with_key.get_token_balance(asset_id=MOCK_ASSET_ID)
    result = json.loads(result_json)

    mock_pw_address.assert_called_once_with(address=MOCK_ADDRESS)
    mock_pw_asset.assert_called_once_with(MOCK_ASSET_ID)
    mock_addr_instance.balance.assert_called_once_with(assetId=MOCK_ASSET_ID)
    assert result["address"] == MOCK_ADDRESS
    assert result["asset_id"] == MOCK_ASSET_ID
    assert result["asset_name"] == "MockToken"
    assert result["balance"] == 500000000
    assert result["formatted_balance"] == "500.000000 MockToken"

@patch('pywaves.Address')
def test_invoke_script_success(mock_pw_address, waves_tools_with_key):
    """Test successful invocation of a dApp script function."""
    # Create mock address instance with invokeScript method
    mock_addr_instance = MagicMock()
    mock_invoke_result = {
        "id": "mockTxId123456789",
        "timestamp": 1678900000000,
        "height": 12345
    }
    mock_addr_instance.invokeScript.return_value = mock_invoke_result
    waves_tools_with_key.address = mock_addr_instance
    
    # Define test parameters
    dapp_address = "3PAbcDefGhiJkLmNoPqRsTuVwXyZ"
    function_name = "deposit"
    params = [
        {"type": "string", "value": "param1"},
        {"type": "integer", "value": 123}
    ]
    payments = [
        {"assetId": "WAVES", "amount": 1.5},  # Should be converted to 150000000 (1.5 * 10^8)
        {"assetId": "mockAssetId", "amount": 100}
    ]
    
    # Create a mock Asset for the non-WAVES asset in payments
    mock_asset = MagicMock()
    type(mock_asset).decimals = PropertyMock(return_value=6)
    
    with patch('pywaves.Asset', return_value=mock_asset):
        # Call the method
        result_json = waves_tools_with_key.invoke_script(
            dapp_address=dapp_address,
            function_name=function_name,
            params=params,
            payments=payments,
            description="Test invocation"
        )
    
    # Parse the result for assertions
    result = json.loads(result_json)
    
    # Verify the invokeScript was called with correct parameters
    expected_payments = [
        {"assetId": "WAVES", "amount": 150000000},  # Converted to wavelets
        {"assetId": "mockAssetId", "amount": 100}   # Not converted because we didn't make it a float
    ]
    
    mock_addr_instance.invokeScript.assert_called_once()
    call_args = mock_addr_instance.invokeScript.call_args[1]
    
    # Basic assertions
    assert result["success"] == True
    assert result["transaction_id"] == "mockTxId123456789"
    assert result["dapp_address"] == dapp_address
    assert result["function"] == function_name
    
    # Detailed parameter assertions
    assert call_args["dappAddress"] == dapp_address
    assert call_args["functionName"] == function_name
    assert call_args["params"] == params
    
    # Ensure payment amount for WAVES was properly converted
    assert len(call_args["payments"]) == 2
    assert call_args["payments"][0]["assetId"] == "WAVES"
    assert call_args["payments"][0]["amount"] == 150000000  # 1.5 WAVES in wavelets

@patch('pywaves.Address')
def test_invoke_script_no_private_key(mock_pw_address, waves_tools_no_key):
    """Test that invoking a script without a private key raises an exception."""
    with pytest.raises(WavesException) as excinfo:
        waves_tools_no_key.invoke_script(
            dapp_address="3PAbcDefGhiJkLmNoPqRsTuVwXyZ",
            function_name="test"
        )
    
    assert "Private key not available" in str(excinfo.value)

@patch('pywaves.Address')
def test_invoke_script_transaction_error(mock_pw_address, waves_tools_with_key):
    """Test handling of a transaction error from the blockchain."""
    # Create mock address instance with invokeScript method that returns an error
    mock_addr_instance = MagicMock()
    mock_invoke_result = {
        "id": "mockTxId123456789",
        "timestamp": 1678900000000,
        "error": "Transaction validation failed: Insufficient funds"
    }
    mock_addr_instance.invokeScript.return_value = mock_invoke_result
    waves_tools_with_key.address = mock_addr_instance
    
    result_json = waves_tools_with_key.invoke_script(
        dapp_address="3PAbcDefGhiJkLmNoPqRsTuVwXyZ",
        function_name="test"
    )
    
    result = json.loads(result_json)
    
    assert result["success"] == False
    assert "error" in result
    assert result["error"] == "Transaction validation failed: Insufficient funds"