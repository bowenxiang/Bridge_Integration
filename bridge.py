from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]


def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
    # 1. Connect to the chain being scanned
    w3 = connect_to(chain)
    
    # 2. Load the private key (Warden)
    try:
        with open('secret_key.txt', 'r') as f:
            private_key = f.read().strip()
    except FileNotFoundError:
        # Fallback for different directory structures
        try:
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(script_dir, 'secret_key.txt')
            with open(key_path, 'r') as f:
                private_key = f.read().strip()
        except Exception as e:
            print(f"Failed to read private key: {e}")
            return 0

    account = w3.eth.account.from_key(private_key)
    
    # 3. Get contract info for the chain being scanned
    contract_details = get_contract_info(chain, contract_info)
    contract_address = contract_details['address']
    contract_abi = contract_details['abi']
    contract = w3.eth.contract(address=contract_address, abi=contract_abi)
    
    # 4. Define Block Range (Look back 5 blocks)
    # We must look back in history to find those transactions.
    latest_block = w3.eth.block_number
    start_block = latest_block - 5
    end_block = latest_block
    
    print(f"Scanning blocks {start_block} to {end_block} on {chain} chain")
    
    # 5. Scan for events
    if chain == 'source':
        # --- Source Chain: Look for DEPOSIT events ---
        try:
            # Use get_logs for reliable historical lookup
            events = contract.events.Deposit.get_logs(fromBlock=start_block, toBlock=end_block)
            
            print(f"Found {len(events)} Deposit events on source chain")
            
            if len(events) > 0:
                # Connect to DESTINATION to execute Wrap
                dest_w3 = connect_to('destination')
                dest_details = get_contract_info('destination', contract_info)
                dest_contract = dest_w3.eth.contract(address=dest_details['address'], abi=dest_details['abi'])
                
                for evt in events:
                    # Extract args
                    token = evt.args['token']
                    recipient = evt.args['recipient']
                    amount = evt.args['amount']
                    
                    print(f"Processing Deposit: token={token}, recipient={recipient}, amount={amount}")
                    
                    # Prepare Transaction
                    nonce = dest_w3.eth.get_transaction_count(account.address)
                    txn = dest_contract.functions.wrap(
                        token, 
                        recipient, 
                        amount
                    ).build_transaction({
                        'from': account.address,
                        'nonce': nonce,
                        # Gas settings can be adjusted if needed
                        'gasPrice': dest_w3.eth.gas_price
                    })
                    
                    # Sign and Send
                    signed_txn = dest_w3.eth.account.sign_transaction(txn, private_key)
                    tx_hash = dest_w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                    
                    print(f"Wrap transaction sent: {tx_hash.hex()}")
                    
                    # Wait for receipt, slows down execution but confirms success
                    dest_w3.eth.wait_for_transaction_receipt(tx_hash)

        except Exception as e:
            print(f"Error processing source events: {e}")

    elif chain == 'destination':
        # --- Destination Chain: Look for UNWRAP events ---
        try:
            # Use get_logs for reliable historical lookup
            events = contract.events.Unwrap.get_logs(fromBlock=start_block, toBlock=end_block)
            
            print(f"Found {len(events)} Unwrap events on destination chain")
            
            if len(events) > 0:
                # Connect to SOURCE to execute Withdraw
                src_w3 = connect_to('source')
                src_details = get_contract_info('source', contract_info)
                src_contract = src_w3.eth.contract(address=src_details['address'], abi=src_details['abi'])
                
                for evt in events:
                    # Extract args
                    underlying_token = evt.args['underlying_token']
                    recipient = evt.args['to']
                    amount = evt.args['amount']
                    
                    print(f"Processing Unwrap: token={underlying_token}, recipient={recipient}, amount={amount}")
                    
                    # Prepare Transaction
                    nonce = src_w3.eth.get_transaction_count(account.address)
                    txn = src_contract.functions.withdraw(
                        underlying_token, 
                        recipient, 
                        amount
                    ).build_transaction({
                        'from': account.address,
                        'nonce': nonce,
                        'gasPrice': src_w3.eth.gas_price
                    })
                    
                    # Sign and Send
                    signed_txn = src_w3.eth.account.sign_transaction(txn, private_key)
                    tx_hash = src_w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                    
                    print(f"Withdraw transaction sent: {tx_hash.hex()}")
                    src_w3.eth.wait_for_transaction_receipt(tx_hash)

        except Exception as e:
            print(f"Error processing destination events: {e}")