# Bitcoin Private Key Balance Checker

A comprehensive tool for validating and checking balances of Bitcoin private keys from text files.

![Bitcoin Key Checker](static/images/banner.png)

## Features

- **Multi-API Support**: Integrates with 12 different blockchain APIs for reliable balance checking
  - Blockchain.info, BlockCypher, Blockstream, Mempool.space, Blockchair
  - Bitaps, BTC.com, Blockonomics, Coinbase, CryptoID, SoChain, BTC Explorer
- **Multiple API Strategies**: Choose between "auto", "rotate", or specific API modes
- **Large File Processing**: Supports files up to 4GB in size
- **Multiple File Formats**: Compatible with .txt, .csv, .list, .dat, .text, .log, .asc, .tsv and .keys
- **Real-time Results**: Displays and saves results as they're found
- **Line Range Processing**: Process specific portions of large files
- **User-friendly Web Interface**: Easy upload and monitoring interface
- **Console Application**: Command-line interface for advanced users
- **Automatic Key Detection**: Extracts and validates private keys from text
- **Real-time Notifications**: Automatically prints complete private key and address when balances are found

## Installation

### Requirements

- Python 3.7 or higher
- Bitcoin Python package
- Requests
- Flask (for web interface)

### Setup

1. Clone this repository:
   ```
   git clone https://github.com/w1k0d3/BitcoinBalanceTracker.git
   cd BitcoinBalanceTracker
   ```

2. Install required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

### Web Interface

1. Start the Flask web server:
   ```
   python main.py
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:5000
   ```

3. Upload your text file containing private keys
4. Configure the processing options
5. Start the job and monitor progress

### Command Line Interface

```
python btc_checker.py -i input_file.txt -o output_file.txt [-d DELAY] [-a API] [-s START_LINE] [-e END_LINE] [-v]
```

Arguments:
- `-i, --input`: Input file containing private keys (required)
- `-o, --output`: Output file to save results (default: found_balances.txt)
- `-d, --delay`: Delay between API requests in seconds (default: 1.0)
- `-a, --api`: API to use for balance checking (default: auto)
  - Options: auto, rotate, blockchain, blockcypher, blockstream, mempool, blockchair, bitaps, btccom, blockonomics, coinbase, cryptoid, sochain, btcexplorer
- `-s, --start`: Start line number (0-indexed, default: 0)
- `-e, --end`: End line number (exclusive, default: process entire file)
- `-v, --verbose`: Enable verbose logging

Example:
```
python btc_checker.py -i private_keys.txt -o results.txt -d 1.5 -a rotate -v
```

## Input File Format

Your input file should contain one private key per line in any of these formats:
- Raw private key (64 hex characters)
- WIF format (Wallet Import Format)
- Mini private key format
- BIP38 encrypted keys (not supported for balance checking, but will be identified)

The tool can also extract private keys from text that contains other content.

## Output Format

The output is saved as a CSV file with the following columns:
- Private Key
- Address
- Balance (BTC)
- Timestamp
- API Used

## API Usage

The tool offers several API strategies:

- **auto**: Automatically selects the most reliable API
- **rotate**: Cycles through all available APIs to avoid rate limiting
- **[specific API]**: Uses only the specified API service

## Performance Considerations

- Use appropriate delay values (0.5-2.0 seconds) to avoid API rate limits
- For very large files, use the line range options to process in batches
- Processing speed depends on network connection and API responsiveness

## Privacy and Security

- All processing is done locally - private keys are never sent to third-party servers
- Only public Bitcoin addresses are sent to blockchain APIs
- Consider running locally when checking valuable private keys

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is provided for educational and research purposes only. Never use this tool on private keys that hold real funds unless you own them. Always use responsibly and ethically.

## Acknowledgements

- Bitcoin Core community
- API providers: Blockchain.info, BlockCypher, Blockstream, and others for their valuable services

For donations:
BTC : 1QBGpio3D5xhTX5ZLicUHzW1uvAzWJDmSE
ETH : 0xe1731Ee4650342ed2d66619a1998E4B3B2e5fb0A 
