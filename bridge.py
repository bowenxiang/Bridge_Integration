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

    # This is different from Bridge IV where chain was "avax" or "bsc"
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
    # Connect to the specified chain
    w3 = connect_to(chain)
    
    # Load the private key for signing transactions
    try:
        with open('secret_key.txt', 'r') as f:
            private_key = f.read().strip()
    except FileNotFoundError:
        # Try alternative path in case running from different directory
        try:
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(script_dir, 'secret_key.txt')
            with open(key_path, 'r') as f:
                private_key = f.read().strip()
        except Exception as e:
            print(f"Failed to read private key: {e}")
            return 0
    except Exception as e:
        print(f"Failed to read private key: {e}")
        return 0
    
    # Get account from private key
    account = w3.eth.account.from_key(private_key)
    
    # Get contract info for the current chain
    contract_details = get_contract_info(chain, contract_info)
    if contract_details == 0:
        return 0
    
    contract_address = contract_details['address']
    contract_abi = contract_details['abi']
    
    # Create contract instance
    contract = w3.eth.contract(address=contract_address, abi=contract_abi)
    
    # Get current block number and calculate range (last 5 blocks)
    current_block = w3.eth.get_block_number()
    start_block = max(0, current_block - 4)  # Last 5 blocks
    end_block = current_block
    
    print(f"Scanning blocks {start_block} to {end_block} on {chain} chain")
    
    # Scan for events based on which chain we're on
    if chain == 'source':
        # Look for Deposit events on source chain
        try:
            # Scan block by block for better reliability
            events = []
            for block_num in range(start_block, end_block + 1):
                try:
                    event_filter = contract.events.Deposit.create_filter(
                        fromBlock=block_num,
                        toBlock=block_num
                    )
                    block_events = event_filter.get_all_entries()
                    events.extend(block_events)
                except Exception as e:
                    # Continue if a specific block fails
                    continue
            
            print(f"Found {len(events)} Deposit events on source chain")
            
            # For each Deposit event, call wrap() on destination chain
            if len(events) > 0:
                # Connect to destination chain
                dest_w3 = connect_to('destination')
                dest_contract_details = get_contract_info('destination', contract_info)
                dest_contract = dest_w3.eth.contract(
                    address=dest_contract_details['address'],
                    abi=dest_contract_details['abi']
                )
                
                for evt in events:
                    token = evt.args['token']
                    recipient = evt.args['recipient']
                    amount = evt.args['amount']
                    
                    print(f"Processing Deposit: token={token}, recipient={recipient}, amount={amount}")
                    
                    # Call wrap() on destination chain
                    try:
                        nonce = dest_w3.eth.get_transaction_count(account.address)
                        
                        # Build transaction
                        txn = dest_contract.functions.wrap(
                            token,  # _underlying_token
                            recipient,  # _recipient
                            amount  # _amount
                        ).build_transaction({
                            'from': account.address,
                            'nonce': nonce,
                            'gas': 200000,
                            'gasPrice': dest_w3.eth.gas_price
                        })
                        
                        # Sign and send transaction
                        signed_txn = dest_w3.eth.account.sign_transaction(txn, private_key)
                        tx_hash = dest_w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                        
                        print(f"Wrap transaction sent: {tx_hash.hex()}")
                        
                        # Wait for transaction receipt
                        tx_receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash)
                        print(f"Wrap transaction confirmed in block {tx_receipt['blockNumber']}")
                        
                    except Exception as e:
                        print(f"Error calling wrap(): {e}")
                        
        except Exception as e:
            print(f"Error scanning for Deposit events: {e}")
    
    elif chain == 'destination':
        # Look for Unwrap events on destination chain
        try:
            # Scan block by block for better reliability
            events = []
            for block_num in range(start_block, end_block + 1):
                try:
                    event_filter = contract.events.Unwrap.create_filter(
                        fromBlock=block_num,
                        toBlock=block_num
                    )
                    block_events = event_filter.get_all_entries()
                    events.extend(block_events)
                except Exception as e:
                    # Continue if a specific block fails
                    continue
            
            print(f"Found {len(events)} Unwrap events on destination chain")
            
            # For each Unwrap event, call withdraw() on source chain
            if len(events) > 0:
                # Connect to source chain
                src_w3 = connect_to('source')
                src_contract_details = get_contract_info('source', contract_info)
                src_contract = src_w3.eth.contract(
                    address=src_contract_details['address'],
                    abi=src_contract_details['abi']
                )
                
                for evt in events:
                    underlying_token = evt.args['underlying_token']
                    recipient = evt.args['to']
                    amount = evt.args['amount']
                    
                    print(f"Processing Unwrap: token={underlying_token}, recipient={recipient}, amount={amount}")
                    
                    # Call withdraw() on source chain
                    try:
                        nonce = src_w3.eth.get_transaction_count(account.address)
                        
                        # Build transaction
                        txn = src_contract.functions.withdraw(
                            underlying_token,  # _token
                            recipient,  # _recipient
                            amount  # _amount
                        ).build_transaction({
                            'from': account.address,
                            'nonce': nonce,
                            'gas': 200000,
                            'gasPrice': src_w3.eth.gas_price
                        })
                        
                        # Sign and send transaction
                        signed_txn = src_w3.eth.account.sign_transaction(txn, private_key)
                        tx_hash = src_w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                        
                        print(f"Withdraw transaction sent: {tx_hash.hex()}")
                        
                        # Wait for transaction receipt
                        tx_receipt = src_w3.eth.wait_for_transaction_receipt(tx_hash)
                        print(f"Withdraw transaction confirmed in block {tx_receipt['blockNumber']}")
                        
                    except Exception as e:
                        print(f"Error calling withdraw(): {e}")
                        
        except Exception as e:
            print(f"Error scanning for Unwrap events: {e}")
    
    return