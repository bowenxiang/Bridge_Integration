from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import sys

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
    return None

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
        return

    # TODO: ENTER YOUR PRIVATE KEY HERE
    # This key must correspond to the address that has the WARDEN_ROLE on the contracts
    # and has funds (AVAX/BNB) on both chains to pay for gas.
    YOUR_PRIVATE_KEY = "bf05816aa7637bb6bd8e7decf92a7cc6b8ff5f2251cd0454ffb6b61809d59336"

    # 1. Setup connections and info
    scan_w3 = connect_to(chain)
    scan_info = get_contract_info(chain, contract_info)

    if chain == 'source':
        target_chain = 'destination'
        event_name = 'Deposit'
    else:
        target_chain = 'source'
        event_name = 'Unwrap'
        
    target_w3 = connect_to(target_chain)
    target_info = get_contract_info(target_chain, contract_info)

    # 2. Validate Private Key and Setup Account
    try:
        account = target_w3.eth.account.from_key(YOUR_PRIVATE_KEY)
        my_address = account.address
    except Exception as e:
        print(f"Error loading private key: {e}")
        return

    # 3. Setup Contracts
    scan_contract = scan_w3.eth.contract(address=scan_info['address'], abi=scan_info['abi'])
    target_contract = target_w3.eth.contract(address=target_info['address'], abi=target_info['abi'])

    # 4. Scan Block Range (Last 5 blocks)
    current_block = scan_w3.eth.block_number
    start_block = current_block - 5
    print(f"Scanning {chain} chain: Blocks {start_block} to {current_block} for {event_name} events.")
    
    # Filter for events
    try:
        # Try Web3.py v6 syntax (snake_case)
        events_filter = scan_contract.events[event_name].create_filter(from_block=start_block, to_block=current_block)
        events = events_filter.get_all_entries()
    except TypeError:
        # Fallback to Web3.py v5 syntax (camelCase)
        events_filter = scan_contract.events[event_name].create_filter(fromBlock=start_block, toBlock=current_block)
        events = events_filter.get_all_entries()
    except Exception as e:
        print(f"Error creating filter: {e}")
        return
    
    if not events:
        print("No events found.")
        return

    # 5. Process Events and Send Transactions
    nonce = target_w3.eth.get_transaction_count(my_address)
    
    for event in events:
        try:
            print(f"Found event in tx: {event['transactionHash'].hex()}")
            args = event['args']
            
            tx = None
            if chain == 'source': 
                # Deposit -> wrap
                token = args['token']
                recipient = args['recipient']
                amount = args['amount']
                
                print(f"Processing Deposit: {amount} of {token} to {recipient}")
                
                tx = target_contract.functions.wrap(token, recipient, amount).build_transaction({
                    'from': my_address,
                    'nonce': nonce,
                    'gasPrice': target_w3.eth.gas_price
                })
                
            else: 
                # Unwrap -> withdraw
                underlying_token = args['underlying_token']
                to = args['to']
                amount = args['amount']
                
                print(f"Processing Unwrap: {amount} of {underlying_token} to {to}")

                tx = target_contract.functions.withdraw(underlying_token, to, amount).build_transaction({
                    'from': my_address,
                    'nonce': nonce,
                    'gasPrice': target_w3.eth.gas_price
                })

            # Sign and Send
            signed_tx = target_w3.eth.account.sign_transaction(tx, YOUR_PRIVATE_KEY)
            
            # Handle both Web3.py v5 (rawTransaction) and v6 (raw_transaction)
            raw_tx = getattr(signed_tx, 'raw_transaction', None) or getattr(signed_tx, 'rawTransaction', None)
            
            tx_hash = target_w3.eth.send_raw_transaction(raw_tx)
            print(f"Transaction sent: {tx_hash.hex()}")
            
            # Increment nonce
            nonce += 1
            
        except Exception as e:
            print(f"Error processing event: {e}")