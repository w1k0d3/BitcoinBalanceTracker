/**
 * Main JavaScript for BTC Key Checker Application
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // File input enhancement
    const fileInput = document.getElementById('file');
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            // Show filename
            const fileName = e.target.files[0]?.name || 'No file chosen';
            const fileLabel = document.querySelector('label[for="file"]');
            
            if (fileLabel) {
                if (fileName !== 'No file chosen') {
                    fileLabel.innerHTML = `<i class="fas fa-file-upload me-2"></i>${fileName}`;
                } else {
                    fileLabel.innerHTML = `<i class="fas fa-file-upload me-2"></i>Select Private Keys File`;
                }
            }
            
            // Validate file extension
            if (fileName !== 'No file chosen') {
                const extension = fileName.split('.').pop().toLowerCase();
                if (extension !== 'txt') {
                    alert('Please select a text (.txt) file');
                    fileInput.value = '';
                    if (fileLabel) {
                        fileLabel.innerHTML = `<i class="fas fa-file-upload me-2"></i>Select Private Keys File`;
                    }
                }
            }
        });
    }
    
    // Form validation
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function(e) {
            const delay = document.getElementById('delay');
            const startLine = document.getElementById('start_line');
            const endLine = document.getElementById('end_line');
            
            let isValid = true;
            
            // Validate delay
            if (delay && (isNaN(parseFloat(delay.value)) || parseFloat(delay.value) < 0.1)) {
                alert('Delay must be a number greater than or equal to 0.1');
                isValid = false;
            }
            
            // Validate start line
            if (startLine && (isNaN(parseInt(startLine.value)) || parseInt(startLine.value) < 0)) {
                alert('Start line must be a non-negative integer');
                isValid = false;
            }
            
            // Validate end line if provided
            if (endLine && endLine.value !== '') {
                if (isNaN(parseInt(endLine.value)) || parseInt(endLine.value) <= parseInt(startLine.value)) {
                    alert('End line must be an integer greater than start line');
                    isValid = false;
                }
            }
            
            if (!isValid) {
                e.preventDefault();
            }
        });
    }
    
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-danger)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});
