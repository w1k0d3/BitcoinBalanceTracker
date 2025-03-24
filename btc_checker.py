#!/usr/bin/env python3
"""
Bitcoin Private Key Balance Checker
This script reads Bitcoin private keys from a text file, validates them,
checks their balance online using multiple APIs, and saves any keys with balances to a file.
"""

import time
import requests
import json
import os
import re
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Callable, Any

# Try to import the bitcoin library, handle error if not available
try:
    from bitcoin import *
except ImportError:
    raise ImportError("Bitcoin library not installed. Please install it with: pip install bitcoin")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_available_apis():
    """
    Return a list of available API options for the UI.
    
    Returns:
        List of API options and descriptions
    """
    return [
        {"value": "auto", "name": "Auto (Try all APIs)", "description": "Automatically try all APIs in sequence until one works"},
        {"value": "rotate", "name": "Round-Robin (Rotate APIs)", "description": "Rotate through all APIs to balance load"},
        {"value": "blockchain", "name": "Blockchain.info", "description": "Use only blockchain.info API"},
        {"value": "blockcypher", "name": "BlockCypher", "description": "Use only BlockCypher API"},
        {"value": "blockstream", "name": "Blockstream.info", "description": "Use only Blockstream.info API"},
        {"value": "mempool", "name": "Mempool.space", "description": "Use only Mempool.space API"},
        {"value": "blockchair", "name": "Blockchair", "description": "Use only Blockchair API"},
        {"value": "bitaps", "name": "Bitaps", "description": "Use only Bitaps API"},
        {"value": "btccom", "name": "BTC.com", "description": "Use only BTC.com API"},
        {"value": "blockonomics", "name": "Blockonomics", "description": "Use only Blockonomics API"},
        {"value": "coinbase", "name": "Coinbase", "description": "Use only Coinbase API"},
        {"value": "cryptoid", "name": "CryptoID", "description": "Use only CryptoID API"},
        {"value": "sochain", "name": "SoChain", "description": "Use only SoChain API"},
        {"value": "btcexplorer", "name": "BTC Explorer", "description": "Use only BTC Explorer API"}
    ]

class BTCKeyChecker:
    def __init__(self, input_file: str, output_file: str, delay: float = 1.0, 
                 api_type: str = "auto", start_line: int = 0, end_line: int = None,
                 logger: logging.Logger = None, progress_callback: Callable = None):
        """
        Initialize the Bitcoin Key Checker.
        
        Args:
            input_file: Path to the text file containing private keys (one per line)
            output_file: Path to save private keys with balances
            delay: Delay between API requests in seconds to avoid rate limiting
            api_type: Specify which API to use ("auto", "rotate", "blockchain", "blockcypher", etc.)
            start_line: Line number to start processing from (0-indexed)
            end_line: Line number to end processing at (exclusive, None for end of file)
            logger: Custom logger to use instead of the default
            progress_callback: Function to call with progress updates
        """
        self.input_file = input_file
        self.output_file_template = output_file
        self.output_file = output_file
        self.delay = delay
        self.max_file_size_bytes = 10000 * 1024 * 1024  # Default 1000 MB
        self.results = []
        self.current_file_index = 0
        self.api_type = api_type
        self.start_line = start_line
        self.end_line = end_line
        self.current_api_index = 0
        self.progress_callback = progress_callback
        
        # Use provided logger or create our own
        self.logger = logger or logging.getLogger(__name__)
        
        # API mapping
        self.api_functions = {
            "blockchain": self._check_balance_blockchain_info,
            "blockcypher": self._check_balance_blockcypher,
            "blockstream": self._check_balance_blockstream,
            "mempool": self._check_balance_mempool,
            "blockchair": self._check_balance_blockchair,
            "bitaps": self._check_balance_bitaps,
            "btccom": self._check_balance_btccom,
            "blockonomics": self._check_balance_blockonomics,
            "coinbase": self._check_balance_coinbase,
            "cryptoid": self._check_balance_cryptoid,
            "sochain": self._check_balance_sochain,
            "btcexplorer": self._check_balance_btcexplorer
        }
        
        # All APIs in a list for rotation
        self.api_list = list(self.api_functions.values())
        
        self.logger.info(f"Initialized with API type: {api_type}, start line: {start_line}, end line: {end_line or 'EOF'}")
    
    def extract_and_validate_private_key(self, line: str) -> Tuple[bool, str]:
        """
        Extract and validate a Bitcoin private key from a line of text.
        The function attempts to find valid private key formats within the text.
        
        Args:
            line: Line of text that might contain a private key
            
        Returns:
            Tuple[bool, str]: (is_valid, private_key)
        """
        # Common Bitcoin private key patterns
        # WIF format (starts with 5, K or L, 51-52 chars)
        wif_pattern = r'[5KL][1-9A-HJ-NP-Za-km-z]{50,51}'
        # Hex format (64 hex chars)
        hex_pattern = r'[0-9a-fA-F]{64}'
        
        # Try to find WIF format
        wif_matches = re.findall(wif_pattern, line)
        for potential_key in wif_matches:
            try:
                privkey_to_pubkey(potential_key)
                self.logger.debug(f"Found valid WIF private key")
                return True, potential_key
            except Exception:
                continue
                
        # Try to find hex format
        hex_matches = re.findall(hex_pattern, line)
        for potential_key in hex_matches:
            try:
                privkey_to_pubkey(potential_key)
                self.logger.debug(f"Found valid HEX private key")
                return True, potential_key
            except Exception:
                continue
        
        # As a last resort, try the whole line
        try:
            cleaned_key = line.strip()
            privkey_to_pubkey(cleaned_key)
            return True, cleaned_key
        except Exception as e:
            self.logger.debug(f"No valid private key found in line: {e}")
            return False, ""
            
    def get_address_from_private_key(self, private_key: str) -> str:
        """
        Generate a Bitcoin address from a private key.
        
        Args:
            private_key: Bitcoin private key
            
        Returns:
            str: Bitcoin address
        """
        pubkey = privkey_to_pubkey(private_key)
        address = pubkey_to_address(pubkey)
        return address
    
    def check_balance(self, address: str) -> Tuple[Optional[float], str]:
        """
        Check the balance of a Bitcoin address using the configured API strategy.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            Tuple: (balance in BTC or None if error, API used)
        """
        try:
            # Auto mode - try all APIs in sequence
            if self.api_type == "auto":
                for api_name, api_func in self.api_functions.items():
                    try:
                        balance = api_func(address)
                        if balance is not None:
                            return balance, api_name
                    except Exception as e:
                        self.logger.warning(f"API {api_name} failed: {e}")
                        continue
                
                self.logger.error(f"All APIs failed for address {address}")
                return None, "unknown"
                
            # Round-robin mode - rotate through APIs
            elif self.api_type == "rotate":
                # Get next API in rotation
                api_name = list(self.api_functions.keys())[self.current_api_index]
                api_func = self.api_functions[api_name]
                # Update index for next call
                self.current_api_index = (self.current_api_index + 1) % len(self.api_functions)
                
                try:
                    balance = api_func(address)
                    return balance, api_name
                except Exception as e:
                    self.logger.warning(f"API {api_name} failed: {e}")
                    return None, "unknown"
                    
            # Specific API mode
            elif self.api_type in self.api_functions:
                api_func = self.api_functions[self.api_type]
                try:
                    balance = api_func(address)
                    return balance, self.api_type
                except Exception as e:
                    self.logger.warning(f"API {self.api_type} failed: {e}")
                    return None, "unknown"
                    
            # Unknown API type
            else:
                self.logger.error(f"Unknown API type: {self.api_type}, falling back to blockchain.info")
                try:
                    balance = self._check_balance_blockchain_info(address)
                    return balance, "blockchain"
                except Exception as e:
                    self.logger.warning(f"Blockchain.info API failed: {e}")
                    return None, "unknown"
                
        except Exception as e:
            self.logger.error(f"Error checking balance: {e}")
            return None, "unknown"
    
    def _check_balance_blockchain_info(self, address: str) -> Optional[float]:
        """Check balance using Blockchain.info API"""
        url = f"https://blockchain.info/balance?active={address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Balance in satoshis, convert to BTC
            balance_satoshi = data[address]['final_balance']
            return balance_satoshi / 100000000
        return None

    def _check_balance_blockcypher(self, address: str) -> Optional[float]:
        """Check balance using BlockCypher API"""
        url = f"https://api.blockcypher.com/v1/btc/main/addrs/{address}/balance"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Balance in satoshis
            balance_satoshi = data['final_balance']
            return balance_satoshi / 100000000
        return None

    def _check_balance_blockstream(self, address: str) -> Optional[float]:
        """Check balance using Blockstream.info API"""
        url = f"https://blockstream.info/api/address/{address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Balance in satoshis
            chain_stats = data.get('chain_stats', {})
            mempool_stats = data.get('mempool_stats', {})
            
            # Combine confirmed and unconfirmed balances
            funded = chain_stats.get('funded_txo_sum', 0) + mempool_stats.get('funded_txo_sum', 0)
            spent = chain_stats.get('spent_txo_sum', 0) + mempool_stats.get('spent_txo_sum', 0)
            
            balance_satoshi = funded - spent
            return balance_satoshi / 100000000
        return None

    def _check_balance_mempool(self, address: str) -> Optional[float]:
        """Check balance using mempool.space API"""
        url = f"https://mempool.space/api/address/{address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Calculate balance from funded and spent amounts
            chain_stats = data.get('chain_stats', {})
            
            funded = chain_stats.get('funded_txo_sum', 0)
            spent = chain_stats.get('spent_txo_sum', 0)
            
            balance_satoshi = funded - spent
            return balance_satoshi / 100000000
        return None

    def _check_balance_blockchair(self, address: str) -> Optional[float]:
        """Check balance using Blockchair API"""
        url = f"https://api.blockchair.com/bitcoin/dashboards/address/{address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Get balance from address data
            address_data = data.get('data', {}).get(address, {})
            balance_satoshi = address_data.get('address', {}).get('balance', 0)
            
            return balance_satoshi / 100000000
        return None
    
    def _check_balance_bitaps(self, address: str) -> Optional[float]:
        """Check balance using Bitaps API"""
        url = f"https://api.bitaps.com/btc/v1/blockchain/address/state/{address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Get balance data
            if data.get('status') == 'success':
                balance_satoshi = data.get('data', {}).get('balance', 0)
                return balance_satoshi / 100000000
        return None
    
    def _check_balance_btccom(self, address: str) -> Optional[float]:
        """Check balance using BTC.com API"""
        url = f"https://chain.api.btc.com/v3/address/{address}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                balance_satoshi = data.get('data', {}).get('balance', 0)
                return balance_satoshi / 100000000
        return None
    
    def _check_balance_blockonomics(self, address: str) -> Optional[float]:
        """Check balance using Blockonomics API"""
        url = f"https://www.blockonomics.co/api/balance"
        headers = {'Content-Type': 'application/json'}
        data = json.dumps({"addr": address})
        
        response = requests.post(url, headers=headers, data=data, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            response_data = data.get('response', [])
            if response_data:
                address_data = response_data[0]
                balance_satoshi = address_data.get('confirmed', 0)
                return balance_satoshi / 100000000
        return None
    
    def _check_balance_coinbase(self, address: str) -> Optional[float]:
        """Check balance using Coinbase API"""
        # Coinbase doesn't have a public address balance API
        # This is a workaround using blockchain.info API with a different user agent
        url = f"https://blockchain.info/balance?active={address}"
        headers = {'User-Agent': 'Coinbase BTC Balance Checker'}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            balance_satoshi = data[address]['final_balance']
            return balance_satoshi / 100000000
        return None
    
    def _check_balance_cryptoid(self, address: str) -> Optional[float]:
        """Check balance using CryptoID API"""
        url = f"https://chainz.cryptoid.info/btc/api.dws?q=getbalance&a={address}"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            try:
                # Response is a plain number
                balance = float(response.text)
                return balance
            except ValueError:
                return None
        return None
        
    def _check_balance_sochain(self, address: str) -> Optional[float]:
        """Check balance using SoChain API"""
        url = f"https://sochain.com/api/v2/get_address_balance/BTC/{address}"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                # Balance already in BTC
                try:
                    balance = float(data.get('data', {}).get('confirmed_balance', 0))
                    return balance
                except (ValueError, TypeError):
                    return None
        return None
        
    def _check_balance_btcexplorer(self, address: str) -> Optional[float]:
        """Check balance using BTC Explorer API"""
        url = f"https://explorer.api.bitcoin.com/btc/v1/addr/{address}/balance"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            try:
                # Response is a plain number in satoshis
                balance_satoshi = int(response.text)
                return balance_satoshi / 100000000
            except (ValueError, TypeError):
                return None
        return None
    
    def get_new_output_filename(self) -> str:
        """
        Generate a new output filename when the current file gets too large.
        
        Returns:
            str: New output filename
        """
        # Split the filename and extension
        base_name, extension = os.path.splitext(self.output_file_template)
        
        # Increment the file index
        self.current_file_index += 1
        
        # Create new filename with index
        new_filename = f"{base_name}_{self.current_file_index:02d}{extension}"
        
        self.logger.info(f"Creating new output file: {new_filename}")
        return new_filename
        
    def check_file_size(self) -> bool:
        """
        Check if the current output file has exceeded the maximum size.
        
        Returns:
            bool: True if file size exceeds limit, False otherwise
        """
        # If file doesn't exist yet, no need to check
        if not os.path.exists(self.output_file):
            return False
            
        try:
            # Get current file size
            file_size = os.path.getsize(self.output_file)
            
            # Check if file size exceeds limit
            if file_size >= self.max_file_size_bytes:
                self.logger.info(f"Current output file size ({file_size/1024/1024:.2f} MB) exceeds limit of {self.max_file_size_bytes/1024/1024:.2f} MB")
                return True
            
            return False
        except Exception as e:
            self.logger.error(f"Error checking file size: {e}")
            return False
    
    def init_output_file(self) -> bool:
        """
        Initialize the output file with headers.
        
        Returns:
            bool: True if initialized successfully, False otherwise
        """
        try:
            # First ensure the directory exists
            output_dir = os.path.dirname(self.output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                self.logger.info(f"Created directory: {output_dir}")
            
            # Check if we need a new file due to size
            try:
                if self.check_file_size():
                    self.output_file = self.get_new_output_filename()
            except Exception as e:
                self.logger.error(f"Error checking file size: {e}")
                # Continue with current filename if check fails
                
            # Check if file exists already
            file_exists = os.path.exists(self.output_file)
            
            # If it doesn't exist, create it with headers
            if not file_exists:
                with open(self.output_file, 'w') as file:
                    file.write("Private Key,Address,Balance (BTC),Timestamp,API Used\n")
                self.logger.info(f"Initialized output file: {self.output_file}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing output file: {e}")
            # Create a backup filename in the current directory if there was an error
            self.output_file = f"found_balances_{int(time.time())}.txt"
            self.logger.info(f"Using backup filename: {self.output_file}")
            
            try:
                with open(self.output_file, 'w') as file:
                    file.write("Private Key,Address,Balance (BTC),Timestamp,API Used\n")
                self.logger.info(f"Initialized backup output file: {self.output_file}")
                return True
            except Exception as e2:
                self.logger.error(f"Could not create backup file either: {e2}")
                return False
    
    def save_result_realtime(self, private_key: str, address: str, balance: float, api_used: str) -> bool:
        """
        Save a single result to output file in real-time when found.
        
        Args:
            private_key: Bitcoin private key
            address: Bitcoin address
            balance: Balance in BTC
            api_used: Name of API used to find this balance
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            # Check if we need to create a new file due to size limit
            if self.check_file_size():
                self.output_file = self.get_new_output_filename()
                # Initialize the new file with headers
                with open(self.output_file, 'w') as file:
                    file.write("Private Key,Address,Balance (BTC),Timestamp,API Used\n")
            
            # Get current timestamp
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Append to the file
            with open(self.output_file, 'a') as file:
                file.write(f"{private_key},{address},{balance},{timestamp},{api_used}\n")
                
            self.logger.info(f"Result saved to {self.output_file} in real-time")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving result in real-time: {e}")
            return False
    
    def process_keys(self) -> List[Dict[str, Any]]:
        """
        Process private keys from the input file within the specified range.
        
        Returns:
            List of dictionaries with private key, address, and balance information
        """
        results = []
        
        # Check if input file exists
        if not os.path.exists(self.input_file):
            self.logger.error(f"Input file not found: {self.input_file}")
            return results
            
        try:
            # Fixed: Added encoding parameter to open
            with open(self.input_file, 'r', encoding='utf-8', errors='replace') as file:
                # Read all lines
                lines = file.readlines()
                
                # Apply line range filtering
                end_line = self.end_line if self.end_line is not None else len(lines)
                lines_to_process = lines[self.start_line:end_line]
            
            total_keys = len(lines_to_process)
            self.logger.info(f"Starting to process {total_keys} private keys from line {self.start_line} to {self.start_line + total_keys}")
            
            for i, line in enumerate(lines_to_process):
                # Get actual line number in the file for logging
                actual_line = i + self.start_line
                
                private_key = line.strip()
                
                if not private_key or private_key.startswith('#'):
                    continue  # Skip empty lines and comments
                
                # Progress update every 10 keys or as requested by progress_callback
                if (i + 1) % 10 == 0 or (i + 1) == total_keys:
                    self.logger.info(f"Progress: {i + 1}/{total_keys} keys processed (lines {self.start_line}-{self.start_line + total_keys})")
                    if self.progress_callback:
                        self.progress_callback(self, i + 1, total_keys, len(results), 
                                               sum(result['balance'] for result in results))
                
                # Extract and validate private key from the line
                is_valid, extracted_key = self.extract_and_validate_private_key(private_key)
                if not is_valid:
                    self.logger.warning(f"Skipping line {actual_line} with no valid private key: {private_key[:30]}...")
                    continue
                
                self.logger.info(f"Found valid private key in line {actual_line}")
                # Get address from the extracted private key
                address = self.get_address_from_private_key(extracted_key)
                # Update private_key to the extracted one for later use
                private_key = extracted_key
                
                self.logger.debug(f"Checking address: {address}")
                
                # Check balance using our check_balance method
                balance, api_used = self.check_balance(address)
                
                # If balance check failed, continue to next key
                if balance is None:
                    self.logger.warning(f"Failed to check balance for {address}")
                    continue
                
                # Log and save if balance found
                if balance > 0:
                    # Print complete private key and address when a key with balance is found
                    print("\n" + "="*80)
                    print(f"BALANCE FOUND!")
                    print(f"Private Key: {private_key}")
                    print(f"Address: {address}")
                    print(f"Balance: {balance} BTC (API: {api_used})")
                    print("="*80 + "\n")
                    
                    # Also log to logger
                    self.logger.info(f"BALANCE FOUND! Private Key: {private_key}")
                    self.logger.info(f"Address: {address} - Balance: {balance} BTC (API: {api_used})")
                    
                    # Save to file in real-time
                    self.save_result_realtime(private_key, address, balance, api_used)
                    
                    # Also keep in our results list for final stats
                    results.append({
                        'private_key': private_key,
                        'address': address,
                        'balance': balance,
                        'api_used': api_used
                    })
                    
                    # If progress callback exists, notify it about the found key with balance
                    if self.progress_callback:
                        self.progress_callback(
                            self, 
                            i + 1, 
                            total_keys, 
                            len(results),
                            sum(result['balance'] for result in results),
                            found_private_key=private_key,
                            found_address=address,
                            found_balance=balance,
                            api_used=api_used
                        )
                
                # Sleep to avoid rate limiting
                time.sleep(self.delay)
                
            return results
            
        except Exception as e:
            self.logger.error(f"Error processing keys: {e}")
            return results
    
    def run(self) -> List[Dict[str, Any]]:
        """
        Run the main process to check all keys and save results.
        
        Returns:
            List of dictionaries with private key, address, and balance information
        """
        self.logger.info("Starting Bitcoin private key balance checker")
        self.logger.info(f"Using API mode: {self.api_type}")
        
        # Initialize output file
        self.init_output_file()
        
        # Process keys
        results = self.process_keys()
        
        # Final summary
        if results:
            total_balance = sum(result['balance'] for result in results)
            self.logger.info(f"Found {len(results)} private keys with balance")
            self.logger.info(f"Total balance found: {total_balance:.8f} BTC")
            
            # API usage stats
            api_stats = {}
            for result in results:
                api_used = result['api_used']
                if api_used in api_stats:
                    api_stats[api_used] += 1
                else:
                    api_stats[api_used] = 1
            
            self.logger.info("API usage statistics:")
            for api, count in api_stats.items():
                self.logger.info(f"  {api}: {count} results")
        else:
            self.logger.info("No private keys with balance found")
            
        self.logger.info("Process completed")
        return results


def main():
    """
    Main function to parse arguments and run the checker from command line.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Check Bitcoin private keys for balances')
    parser.add_argument('-i', '--input', required=True, help='Input file containing private keys')
    parser.add_argument('-o', '--output', default='found_balances.txt', help='Output file to save results')
    parser.add_argument('-d', '--delay', type=float, default=1.0, help='Delay between API requests in seconds')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('-a', '--api', choices=['auto', 'rotate', 'blockchain', 'blockcypher', 'blockstream', 
                                               'mempool', 'blockchair', 'bitaps', 'btccom', 'blockonomics',
                                               'coinbase', 'cryptoid', 'sochain', 'btcexplorer'], 
                        default='auto', help='API to use for balance checking')
    parser.add_argument('-s', '--start', type=int, default=0, help='Start line number (0-indexed)')
    parser.add_argument('-e', '--end', type=int, default=None, help='End line number (exclusive)')
    
    args = parser.parse_args()
    
    # Set debug level if verbose
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run the checker
    checker = BTCKeyChecker(args.input, args.output, args.delay, args.api, args.start, args.end)
    checker.run()


if __name__ == "__main__":
    main()
