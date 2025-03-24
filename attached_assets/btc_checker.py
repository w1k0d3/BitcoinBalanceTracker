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
from bitcoin import *
import logging
from typing import Dict, List, Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BTCKeyChecker:
    def __init__(self, input_file: str, output_file: str, delay: float = 1.0, api_type: str = "auto", start_line: int = 0, end_line: int = None):
        """
        Initialize the Bitcoin Key Checker.
        
        Args:
            input_file: Path to the text file containing private keys (one per line)
            output_file: Path to save private keys with balances
            delay: Delay between API requests in seconds to avoid rate limiting
            api_type: Specify which API to use ("auto", "rotate", "blockchain", "blockcypher", "blockstream", "mempool", "blockchair")
            start_line: Line number to start processing from (0-indexed)
            end_line: Line number to end processing at (exclusive, None for end of file)
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
        
        # API mapping
        self.api_functions = {
            "blockchain": self._check_balance_blockchain_info,
            "blockcypher": self._check_balance_blockcypher,
            "blockstream": self._check_balance_blockstream,
            "mempool": self._check_balance_mempool,
            "blockchair": self._check_balance_blockchair
        }
        
        # All APIs in a list for rotation
        self.api_list = list(self.api_functions.values())
        
        logger.info(f"Initialized with API type: {api_type}, start line: {start_line}, end line: {end_line or 'EOF'}")
    
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
        
        import re
        
        # Try to find WIF format
        wif_matches = re.findall(wif_pattern, line)
        for potential_key in wif_matches:
            try:
                privkey_to_pubkey(potential_key)
                logger.debug(f"Found valid WIF private key")
                return True, potential_key
            except:
                continue
                
        # Try to find hex format
        hex_matches = re.findall(hex_pattern, line)
        for potential_key in hex_matches:
            try:
                privkey_to_pubkey(potential_key)
                logger.debug(f"Found valid HEX private key")
                return True, potential_key
            except:
                continue
        
        # As a last resort, try the whole line
        try:
            cleaned_key = line.strip()
            privkey_to_pubkey(cleaned_key)
            return True, cleaned_key
        except Exception as e:
            logger.debug(f"No valid private key found in line: {e}")
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
    
    def check_balance(self, address: str) -> Optional[float]:
        """
        Check the balance of a Bitcoin address using the configured API strategy.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            float: Balance in BTC or None if error
        """
        try:
            # Auto mode - try all APIs in sequence
            if self.api_type == "auto":
                for api_func in self.api_list:
                    try:
                        balance = api_func(address)
                        if balance is not None:
                            return balance
                    except Exception as e:
                        logger.warning(f"API {api_func.__name__} failed: {e}")
                        continue
                
                logger.error(f"All APIs failed for address {address}")
                return None
                
            # Round-robin mode - rotate through APIs
            elif self.api_type == "rotate":
                # Get next API in rotation
                api_func = self.api_list[self.current_api_index]
                # Update index for next call
                self.current_api_index = (self.current_api_index + 1) % len(self.api_list)
                
                try:
                    return api_func(address)
                except Exception as e:
                    logger.warning(f"API {api_func.__name__} failed: {e}")
                    return None
                    
            # Specific API mode
            elif self.api_type in self.api_functions:
                api_func = self.api_functions[self.api_type]
                try:
                    return api_func(address)
                except Exception as e:
                    logger.warning(f"API {self.api_type} failed: {e}")
                    return None
                    
            # Unknown API type
            else:
                logger.error(f"Unknown API type: {self.api_type}, falling back to blockchain.info")
                return self._check_balance_blockchain_info(address)
                
        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            return None
    
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
        
        logger.info(f"Creating new output file: {new_filename}")
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
                logger.info(f"Current output file size ({file_size/1024/1024:.2f} MB) exceeds limit of {self.max_file_size_bytes/1024/1024:.2f} MB")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking file size: {e}")
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
                logger.info(f"Created directory: {output_dir}")
            
            # Check if we need a new file due to size
            try:
                if self.check_file_size():
                    self.output_file = self.get_new_output_filename()
            except Exception as e:
                logger.error(f"Error checking file size: {e}")
                # Continue with current filename if check fails
                
            # Check if file exists already
            file_exists = os.path.exists(self.output_file)
            
            # If it doesn't exist, create it with headers
            if not file_exists:
                with open(self.output_file, 'w') as file:
                    file.write("Private Key,Address,Balance (BTC),Timestamp,API Used\n")
                logger.info(f"Initialized output file: {self.output_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing output file: {e}")
            # Create a backup filename in the current directory if there was an error
            self.output_file = f"found_balances_{int(time.time())}.txt"
            logger.info(f"Using backup filename: {self.output_file}")
            
            try:
                with open(self.output_file, 'w') as file:
                    file.write("Private Key,Address,Balance (BTC),Timestamp,API Used\n")
                logger.info(f"Initialized backup output file: {self.output_file}")
                return True
            except Exception as e2:
                logger.error(f"Could not create backup file either: {e2}")
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
                
            logger.info(f"Result saved to {self.output_file} in real-time")
            return True
            
        except Exception as e:
            logger.error(f"Error saving result in real-time: {e}")
            return False
    
    def process_keys(self) -> List[Dict[str, str]]:
        """
        Process private keys from the input file within the specified range.
        
        Returns:
            List of dictionaries with private key, address, and balance information
        """
        results = []
        
        # Check if input file exists
        if not os.path.exists(self.input_file):
            logger.error(f"Input file not found: {self.input_file}")
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
            logger.info(f"Starting to process {total_keys} private keys from line {self.start_line} to {self.start_line + total_keys}")
            
            for i, line in enumerate(lines_to_process):
                # Get actual line number in the file for logging
                actual_line = i + self.start_line
                
                private_key = line.strip()
                
                if not private_key or private_key.startswith('#'):
                    continue  # Skip empty lines and comments
                
                # Progress update every 10 keys
                if (i + 1) % 10 == 0 or (i + 1) == total_keys:
                    logger.info(f"Progress: {i + 1}/{total_keys} keys processed (lines {self.start_line}-{self.start_line + total_keys})")
                
                # Extract and validate private key from the line
                is_valid, extracted_key = self.extract_and_validate_private_key(private_key)
                if not is_valid:
                    logger.warning(f"Skipping line {actual_line} with no valid private key: {private_key[:30]}...")
                    continue
                
                logger.info(f"Found valid private key in line {actual_line}")
                # Get address from the extracted private key
                address = self.get_address_from_private_key(extracted_key)
                # Update private_key to the extracted one for later use
                private_key = extracted_key
                
                logger.debug(f"Checking address: {address}")
                
                # Track which API was used successfully
                api_used = "unknown"
                
                # Auto mode - try all APIs in sequence
                if self.api_type == "auto":
                    for api_name, api_func in self.api_functions.items():
                        try:
                            balance = api_func(address)
                            if balance is not None:
                                api_used = api_name
                                break
                        except Exception as e:
                            logger.warning(f"API {api_name} failed: {e}")
                            continue
                    
                    if api_used == "unknown":
                        logger.error(f"All APIs failed for address {address}")
                        continue
                
                # Round-robin mode - rotate through APIs
                elif self.api_type == "rotate":
                    # Get next API in rotation
                    api_name = list(self.api_functions.keys())[self.current_api_index]
                    api_func = self.api_functions[api_name]
                    # Update index for next call
                    self.current_api_index = (self.current_api_index + 1) % len(self.api_functions)
                    
                    try:
                        balance = api_func(address)
                        if balance is not None:
                            api_used = api_name
                    except Exception as e:
                        logger.warning(f"API {api_name} failed: {e}")
                        continue
                
                # Specific API mode
                elif self.api_type in self.api_functions:
                    api_used = self.api_type
                    try:
                        balance = self.api_functions[self.api_type](address)
                    except Exception as e:
                        logger.warning(f"API {self.api_type} failed: {e}")
                        continue
                
                # Unknown API type - use blockchain.info as fallback
                else:
                    api_used = "blockchain"
                    try:
                        balance = self._check_balance_blockchain_info(address)
                    except Exception as e:
                        logger.warning(f"Blockchain.info API failed: {e}")
                        continue
                
                if balance is None:
                    logger.warning(f"Failed to check balance for {address}")
                    continue
                
                # Log and save if balance found
                if balance > 0:
                    logger.info(f"BALANCE FOUND! Address: {address} - Balance: {balance} BTC (API: {api_used})")
                    
                    # Save to file in real-time
                    self.save_result_realtime(private_key, address, balance, api_used)
                    
                    # Also keep in our results list for final stats
                    results.append({
                        'private_key': private_key,
                        'address': address,
                        'balance': balance,
                        'api_used': api_used
                    })
                
                # Sleep to avoid rate limiting
                time.sleep(self.delay)
                
            return results
            
        except Exception as e:
            logger.error(f"Error processing keys: {e}")
            return results
    
    def run(self) -> None:
        """
        Run the main process to check all keys and save results.
        """
        logger.info("Starting Bitcoin private key balance checker")
        logger.info(f"Using API mode: {self.api_type}")
        
        # Initialize output file
        self.init_output_file()
        
        # Process keys
        results = self.process_keys()
        
        # Final summary
        if results:
            total_balance = sum(result['balance'] for result in results)
            logger.info(f"Found {len(results)} private keys with balance")
            logger.info(f"Total balance found: {total_balance:.8f} BTC")
            
            # API usage stats
            api_stats = {}
            for result in results:
                api_used = result['api_used']
                if api_used in api_stats:
                    api_stats[api_used] += 1
                else:
                    api_stats[api_used] = 1
            
            logger.info("API usage statistics:")
            for api, count in api_stats.items():
                logger.info(f"  {api}: {count} results")
        else:
            logger.info("No private keys with balance found")
            
        logger.info("Process completed")


def main():
    """
    Main function to parse arguments and run the checker.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Check Bitcoin private keys for balances')
    parser.add_argument('-i', '--input', required=True, help='Input file containing private keys')
    parser.add_argument('-o', '--output', default='found_balances.txt', help='Output file to save results')
    parser.add_argument('-d', '--delay', type=float, default=1.0, help='Delay between API requests in seconds')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('-a', '--api', choices=['auto', 'rotate', 'blockchain', 'blockcypher', 'blockstream', 'mempool', 'blockchair'], 
                        default='auto', help='API to use for balance checking')
    parser.add_argument('-s', '--start', type=int, default=0, help='Start line number (0-indexed)')
    parser.add_argument('-e', '--end', type=int, default=None, help='End line number (exclusive)')
    parser.add_argument('-p', '--progress', type=int, default=10, 
                        help='Report progress every N keys (default: 10)')
    
    args = parser.parse_args()
    
    # Set debug level if verbose
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Create and run the checker
    checker = BTCKeyChecker(args.input, args.output, args.delay, args.api, args.start, args.end)
    checker.run()


if __name__ == "__main__":
    main()