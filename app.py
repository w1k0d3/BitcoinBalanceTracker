import os
import re
import time
import json
import uuid
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_file, session
from werkzeug.utils import secure_filename
import threading
from btc_checker import BTCKeyChecker, get_available_apis

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "bitcoin_checker_secret_key")

# App configuration
UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'results'
ALLOWED_EXTENSIONS = {'txt', 'csv', 'list', 'dat', 'text', 'log', 'asc', 'tsv', 'keys'}
MAX_CONTENT_LENGTH = 4 * 1024 * 1024 * 1024  # 4GB limit

# Create necessary directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Store running jobs
running_jobs = {}

def allowed_file(filename):
    """Check if the file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Render the main page with the form."""
    api_options = get_available_apis()
    return render_template(
        'index.html',
        api_options=api_options,
        running_jobs=running_jobs
    )

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and start the balance checking process."""
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('index'))
    
    if not allowed_file(file.filename):
        flash(f'Invalid file type. Please upload a file with one of these extensions: {", ".join(ALLOWED_EXTENSIONS)}', 'danger')
        return redirect(url_for('index'))
    
    # Get form parameters
    api_type = request.form.get('api_type', 'auto')
    delay = float(request.form.get('delay', 1.0))
    start_line = int(request.form.get('start_line', 0))
    end_line = request.form.get('end_line', '')
    end_line = int(end_line) if end_line.isdigit() else None
    
    # Generate unique job ID and filenames
    job_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_filename = f"{job_id}_{secure_filename(file.filename)}"
    output_filename = f"results_{job_id}_{timestamp}.csv"
    
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
    output_path = os.path.join(app.config['RESULTS_FOLDER'], output_filename)
    
    # Save the uploaded file
    file.save(input_path)
    
    # Create job info with all necessary defaults
    job_info = {
        'id': job_id,
        'status': 'running',
        'start_time': time.time(),
        'filename': file.filename,
        'api_type': api_type,
        'delay': delay,
        'start_line': start_line,
        'end_line': end_line,
        'input_path': input_path,
        'output_path': output_path,
        'progress': 0,
        'keys_processed': 0,
        'total_keys': 0,
        'found_keys': 0,
        'total_balance': 0.0,
        'last_update': time.time(),
        'log': [],
        'duration': 0,     # Add default duration
        'api_stats': {},   # Add default api_stats
        'error': None      # Add default error message field
    }
    
    # Count total lines/keys using a streaming approach for large files
    try:
        total_lines = 0
        with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
            # Process in batches to be memory efficient
            for i, _ in enumerate(f):
                if i % 10000 == 0:  # Log progress every 10K lines
                    logger.info(f"Counting lines: {i} lines processed so far...")
                total_lines = i + 1
        logger.info(f"Total lines in file: {total_lines}")
    except Exception as e:
        logger.warning(f"Error counting lines: {e}")
        # Set a default if counting fails
        total_lines = 1000  # Arbitrary default
    
    job_info['total_keys'] = total_lines - start_line if end_line is None else min(end_line, total_lines) - start_line
    
    # Store job info
    running_jobs[job_id] = job_info
    
    # Start the processing in a background thread
    thread = threading.Thread(
        target=process_file,
        args=(job_id, input_path, output_path, api_type, delay, start_line, end_line)
    )
    thread.daemon = True
    thread.start()
    
    flash(f'File uploaded successfully! Processing started with job ID: {job_id}', 'success')
    return redirect(url_for('view_results', job_id=job_id))

def process_file(job_id, input_file, output_file, api_type, delay, start_line, end_line):
    """Process the uploaded file in a background thread."""
    job_info = running_jobs[job_id]
    
    try:
        # Create custom logger handler to capture logs for the web UI
        class WebUILogHandler(logging.Handler):
            def emit(self, record):
                log_entry = self.format(record)
                job_info['log'].append({
                    'time': time.strftime("%H:%M:%S"),
                    'level': record.levelname,
                    'message': record.getMessage()
                })
                # Keep only the last 100 log entries
                job_info['log'] = job_info['log'][-100:]
                job_info['last_update'] = time.time()

        logger = logging.getLogger(f'job_{job_id}')
        handler = WebUILogHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(handler)
        
        # Override progress update method
        def update_progress(checker, i, total, found_keys=None, total_balance=None, 
                           found_private_key=None, found_address=None, found_balance=None, api_used=None):
            job_info['keys_processed'] = i
            job_info['progress'] = min(100, int((i / total) * 100)) if total > 0 else 0
            if found_keys is not None:
                job_info['found_keys'] = found_keys
            if total_balance is not None:
                job_info['total_balance'] = total_balance
                
            # Capture and display found keys with balances
            if found_private_key and found_address and found_balance:
                # Add to found keys list in job_info
                if 'found_key_details' not in job_info:
                    job_info['found_key_details'] = []
                
                job_info['found_key_details'].append({
                    'private_key': found_private_key,
                    'address': found_address,
                    'balance': found_balance,
                    'api_used': api_used,
                    'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
                })
                
                # Log the found key
                logger.info(f"BALANCE FOUND! Private Key: {found_private_key}")
                logger.info(f"Address: {found_address} - Balance: {found_balance} BTC (API: {api_used})")
                
            job_info['last_update'] = time.time()

        # Create and run checker
        checker = BTCKeyChecker(
            input_file=input_file,
            output_file=output_file,
            delay=delay,
            api_type=api_type,
            start_line=start_line,
            end_line=end_line,
            logger=logger,
            progress_callback=update_progress
        )
        
        results = checker.run()
        
        # Update final statistics
        if results:
            job_info['found_keys'] = len(results)
            job_info['total_balance'] = sum(result['balance'] for result in results)
            
            # API usage stats
            api_stats = {}
            for result in results:
                api_used = result['api_used']
                if api_used in api_stats:
                    api_stats[api_used] += 1
                else:
                    api_stats[api_used] = 1
            
            job_info['api_stats'] = api_stats
        
        job_info['status'] = 'completed'
        job_info['end_time'] = time.time()
        job_info['duration'] = job_info['end_time'] - job_info['start_time']
        
    except Exception as e:
        logger.error(f"Error in processing job: {str(e)}")
        job_info['status'] = 'failed'
        job_info['error'] = str(e)
        job_info['end_time'] = time.time()
        job_info['duration'] = job_info['end_time'] - job_info['start_time']

@app.route('/results/<job_id>')
def view_results(job_id):
    """View the results page for a specific job."""
    if job_id not in running_jobs:
        flash('Job not found', 'danger')
        return redirect(url_for('index'))
    
    job_info = running_jobs[job_id]
    return render_template('results.html', job=job_info)

@app.route('/api/job/<job_id>')
def get_job_status(job_id):
    """API endpoint to get the current status of a job."""
    if job_id not in running_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(running_jobs[job_id])

@app.route('/download/<job_id>')
def download_results(job_id):
    """Download the results file for a completed job."""
    if job_id not in running_jobs:
        flash('Job not found', 'danger')
        return redirect(url_for('index'))
    
    job_info = running_jobs[job_id]
    
    if job_info['status'] != 'completed':
        flash('Results not ready for download', 'warning')
        return redirect(url_for('view_results', job_id=job_id))
    
    if not os.path.exists(job_info['output_path']):
        flash('Results file not found', 'danger')
        return redirect(url_for('view_results', job_id=job_id))
    
    return send_file(
        job_info['output_path'],
        as_attachment=True,
        download_name=f"btc_balance_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

@app.route('/cancel/<job_id>')
def cancel_job(job_id):
    """Cancel a running job."""
    if job_id not in running_jobs:
        flash('Job not found', 'danger')
        return redirect(url_for('index'))
    
    job_info = running_jobs[job_id]
    
    if job_info['status'] == 'running':
        job_info['status'] = 'cancelled'
        # Set end time and duration for cancelled jobs
        job_info['end_time'] = time.time()
        job_info['duration'] = job_info['end_time'] - job_info['start_time']
        flash('Job cancelled successfully', 'success')
    else:
        flash('Job is not running, cannot cancel', 'warning')
    
    return redirect(url_for('view_results', job_id=job_id))

@app.route('/clear/<job_id>')
def clear_job(job_id):
    """Remove a completed or failed job from the list."""
    if job_id not in running_jobs:
        flash('Job not found', 'danger')
        return redirect(url_for('index'))
    
    job_info = running_jobs[job_id]
    
    if job_info['status'] in ['completed', 'failed', 'cancelled']:
        # Delete input file if it exists
        try:
            if os.path.exists(job_info['input_path']):
                os.remove(job_info['input_path'])
        except Exception as e:
            logger.error(f"Error deleting input file: {str(e)}")
        
        # Remove job from running jobs
        del running_jobs[job_id]
        flash('Job cleared successfully', 'success')
    else:
        flash('Cannot clear a running job', 'warning')
    
    return redirect(url_for('index'))

@app.template_filter('format_time')
def format_time(seconds):
    """Format time in seconds to readable format."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
