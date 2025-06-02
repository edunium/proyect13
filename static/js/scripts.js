// Main JavaScript file for the Municipal Records System

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Add fade-in class to main container for smooth page transitions
    document.querySelector('main.container').classList.add('fade-in');
    
    // Alert auto-close after 5 seconds
    setTimeout(function() {
        var alertList = [].slice.call(document.querySelectorAll('.alert:not(.alert-permanent)'));
        alertList.forEach(function (alert) {
            var alertInstance = new bootstrap.Alert(alert);
            alertInstance.close();
        });
    }, 5000);
    
    // Department filter change handler
    const departmentFilter = document.getElementById('department-filter');
    if (departmentFilter) {
        departmentFilter.addEventListener('change', function() {
            if (this.value) {
                window.location.href = `/records?department=${this.value}`;
            } else {
                window.location.href = '/records';
            }
        });
    }
    
    // Record status change handler
    const statusButtons = document.querySelectorAll('.status-change-btn');
    statusButtons.forEach(button => {
        button.addEventListener('click', function() {
            const recordId = this.getAttribute('data-record-id');
            const newStatus = this.getAttribute('data-status');
            
            if (confirm(`¿Está seguro que desea cambiar el estado a "${newStatus}"?`)) {
                // Here would go the code to update the record status
                console.log(`Changing status of record ${recordId} to ${newStatus}`);
            }
        });
    });
    
    // Form validation
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });
    
    // Search functionality
    const searchInput = document.querySelector('.search-records');
    if (searchInput) {
        searchInput.addEventListener('keyup', function() {
            const searchTerm = this.value.toLowerCase();
            const recordRows = document.querySelectorAll('tbody tr');
            
            recordRows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if(text.includes(searchTerm)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }
});

// Function to preview record details in a modal
function previewRecord(recordId) {
    // This would be an AJAX call to get record details
    console.log(`Previewing record ${recordId}`);
    
    // Show loading state
    document.getElementById('recordPreviewBody').innerHTML = '<div class="text-center"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Cargando...</span></div></div>';
    
    // Show the modal
    const previewModal = new bootstrap.Modal(document.getElementById('recordPreviewModal'));
    previewModal.show();
    
    // Simulate loading data (in a real app, this would be an AJAX call)
    setTimeout(() => {
        document.getElementById('recordPreviewBody').innerHTML = `
            <h5>Título del Expediente #${recordId}</h5>
            <p>Descripción del expediente...</p>
            <p><strong>Departamento:</strong> Obras Públicas</p>
            <p><strong>Estado:</strong> <span class="badge bg-success">Activo</span></p>
        `;
    }, 1000);
}

// Print record function
function printRecord(recordId) {
    console.log(`Printing record ${recordId}`);
    window.print();
}