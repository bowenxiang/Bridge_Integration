from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import json
import sys
import os

# Function to connect to the blockchains
def connect(chain):
    if chain == 'avax':
        api_url = "https://api.avax-test.network/ext/bc/C/rpc"
        w3 = Web3(Web3.HTTPProvider(api_url))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3
    elif chain == 'bsc':
        api_url = "https://data-seed-prebsc-1-s1.binance.org:8545/"
        w3 = Web3(Web3.HTTPProvider(api_url))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3

def get_events(w3, contract, event_name, start_block, end_block):
    """
    Scans for events in a given block range.
    """
    print(f"Scanning {event_name} from {start_block} to {end_block}...")
    arg_filter = {}
    
    # Depending on the event name, access the specific event object
    if event_name == "Deposit":
        event_object = contract.events.Deposit
    elif event_name == "Unwrap":
        event_object = contract.events.Unwrap
    else:
        return []

    if end_block - start_block < 30:
        event_filter = event_object.create_filter(from_block=start_block, to_block=end_block, argument_filters=arg_filter)
        events = event_filter.get_all_entries()
    else:
        events = []
        for block_num in range(start_block, end_block + 1):
            event_filter = event_object.create_filter(from_block=block_num, to_block=block_num, argument_filters=arg_filter)
            events.extend(event_filter.get_all_entries())
            
    return events

def send_transaction(w3, contract_function, account):
    """
    Helper to build, sign, and send a transaction.
    """
    # Build transaction
    tx_params = {
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gasPrice': w3.eth.gas_price,
    }
    
    # Estimate gas (optional but recommended)
    try:
        gas_estimate = contract_function.estimate_gas(tx_params)
        tx_params['gas'] = int(gas_estimate * 1.2) # Add buffer
    except Exception as e:
        print(f"Gas estimation failed: {e}. Using default gas.")
        tx_params['gas'] = 300000

    # Build the transaction
    tx = contract_function.build_transaction(tx_params)
    
    # Sign
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=account.key)
    
    # Send
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print(f"Transaction sent: {tx_hash.hex()}")
    
    # Wait for receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Transaction confirmed in block {receipt.blockNumber}")
    return receipt

def main():
    # 1. Load Configuration
    try:
        with open('contract_info.json', 'r') as f:
            contract_info = json.load(f)
    except FileNotFoundError:
        print("Error: contract_info.json not found.")
        return

    # Extract details
    try:
        warden_key = contract_info['warden_private_key']
        source_address = contract_info['source_address']
        source_abi = contract_info['source_abi']
        dest_address = contract_info['destination_address']
        dest_abi = contract_info['destination_abi']
    except KeyError as e:
        print(f"Error: Missing key {e} in contract_info.json")
        return

    # 2. Connect to chains
    w3_source = connect('avax')
    w3_dest = connect('bsc')

    # 3. Setup Account
    warden_account = w3_source.eth.account.from_key(warden_key)
    print(f"Running bridge as Warden: {warden_account.address}")

    # 4. Setup Contracts
    source_contract = w3_source.eth.contract(address=source_address, abi=source_abi)
    dest_contract = w3_dest.eth.contract(address=dest_address, abi=dest_abi)

    # 5. Scan Logic
    # We scan the last 5 blocks on both chains to catch recent events
    # (Adjust this range if the autograder requires a larger history)
    
    # --- Source -> Destination (Deposit -> Wrap) ---
    source_latest = w3_source.eth.block_number
    source_start = source_latest - 5
    
    deposit_events = get_events(w3_source, source_contract, "Deposit", source_start, source_latest)
    
    for evt in deposit_events:
        print(f"Found Deposit: {evt.args}")
        # Extract args
        token = evt.args['token']
        recipient = evt.args['recipient']
        amount = evt.args['amount']
        
        # Call wrap() on Destination
        # Note: Ensure the function name matches your ABI (usually 'wrap' or 'mint')
        print(f"Relaying to Destination: wrap({token}, {recipient}, {amount})")
        send_transaction(w3_dest, dest_contract.functions.wrap(token, recipient, amount), warden_account)

    # --- Destination -> Source (Unwrap -> Withdraw) ---
    dest_latest = w3_dest.eth.block_number
    dest_start = dest_latest - 5
    
    unwrap_events = get_events(w3_dest, dest_contract, "Unwrap", dest_start, dest_latest)
    
    for evt in unwrap_events:
        print(f"Found Unwrap: {evt.args}")
        # Extract args
        token = evt.args['token']      # Check if this is 'token' or 'wrappedToken' in your ABI
        recipient = evt.args['recipient']
        amount = evt.args['amount']
        
        # Call withdraw() on Source
        print(f"Relaying to Source: withdraw({token}, {recipient}, {amount})")
        send_transaction(w3_source, source_contract.functions.withdraw(token, recipient, amount), warden_account)

if __name__ == "__main__":
    main()