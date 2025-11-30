def main():
    # 1. Load Configuration
    try:
        with open('contract_info.json', 'r') as f:
            contract_info = json.load(f)
    except FileNotFoundError:
        print("Error: contract_info.json not found.")
        return

    # Extract details (Updated for Nested JSON Structure)
    try:
        warden_key = contract_info['warden_private_key']
        
        # Access nested keys
        source_address = contract_info['source']['address']
        source_abi = contract_info['source']['abi']
        
        dest_address = contract_info['destination']['address']
        dest_abi = contract_info['destination']['abi']
        
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

    # 5. Scan Logic (Same as before)
    # --- Source -> Destination (Deposit -> Wrap) ---
    source_latest = w3_source.eth.block_number
    source_start = source_latest - 5
    
    deposit_events = get_events(w3_source, source_contract, "Deposit", source_start, source_latest)
    
    for evt in deposit_events:
        print(f"Found Deposit: {evt.args}")
        token = evt.args['token']
        recipient = evt.args['recipient']
        amount = evt.args['amount']
        print(f"Relaying to Destination: wrap({token}, {recipient}, {amount})")
        send_transaction(w3_dest, dest_contract.functions.wrap(token, recipient, amount), warden_account)

    # --- Destination -> Source (Unwrap -> Withdraw) ---
    dest_latest = w3_dest.eth.block_number
    dest_start = dest_latest - 5
    
    unwrap_events = get_events(w3_dest, dest_contract, "Unwrap", dest_start, dest_latest)
    
    for evt in unwrap_events:
        print(f"Found Unwrap: {evt.args}")
        token = evt.args['token']
        recipient = evt.args['recipient']
        amount = evt.args['amount']
        print(f"Relaying to Source: withdraw({token}, {recipient}, {amount})")
        send_transaction(w3_source, source_contract.functions.withdraw(token, recipient, amount), warden_account)