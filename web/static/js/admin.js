console.log('Admin panel initialized');
window.ADMIN_JS_VERSION = '3.1';

class AdminPanel {
    constructor() {
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.updateTimestamps();
        this.updateConnectionStatus();
        
        setInterval(() => this.updateTimestamps(), 60000);
        
        console.log('AdminPanel initialized (no WebSocket)');
    }
    
    updateConnectionStatus() {
        const statusElement = document.getElementById('websocketStatus');
        if (statusElement) {
            statusElement.className = 'badge bg-success';
            statusElement.innerHTML = '<i class="fas fa-check-circle"></i> Готов';
        }
    }
    
    setupEventListeners() {

        document.addEventListener('submit', (e) => {
            console.log('Submit event detected on:', e.target);
            console.log('Has ajax-form class:', e.target.classList.contains('ajax-form'));
            

            if (e.target.classList.contains('ajax-form') && !e.target.dataset.hasLocalHandler) {
                e.preventDefault();
                console.log('Preventing default and calling handleAjaxForm');
                this.handleAjaxForm(e.target);
            }
        });
        

        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('ajax-btn') || e.target.closest('.ajax-btn')) {
                e.preventDefault();
                const button = e.target.classList.contains('ajax-btn') ? e.target : e.target.closest('.ajax-btn');
                this.handleAjaxButton(button);
            }
            
            const target = e.target.closest('[data-action]');
            if (target) {
                this.handleAction(target.dataset.action);
            }
        });
        

        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }
    
    handleAction(action) {
        switch (action) {
            case 'refresh':
                window.location.reload();
                break;
            case 'toggle-filter':
                const filterCard = document.querySelector('.filter-form');
                if (filterCard) {
                    filterCard.style.display = filterCard.style.display === 'none' ? 'block' : 'none';
                }
                break;
        }
    }
    
    async handleAjaxForm(form) {
        console.log('handleAjaxForm called with form:', form);
        console.log('Form action:', form.action);
        console.log('Form method:', form.method);
        
        const formData = new FormData(form);
        const button = form.querySelector('button[type="submit"]');
        

        for (let [key, value] of formData.entries()) {
            console.log('Form data:', key, '=', value);
        }
        
        try {
            this.showLoading(button);
            
            const response = await fetch(form.action, {
                method: form.method || 'POST',
                body: formData
            });
            
            console.log('Response status:', response.status);
            const result = await response.json();
            console.log('Response result:', result);
            
            if (result.success) {
                this.showToast(result.message || 'Операция выполнена успешно', 'success');
                

                if (result.appeal_id && result.status) {
                    this.updateAppealStatusInTable(result.appeal_id, result.status);
                }
                

                const modal = form.closest('.modal');
                if (modal) {
                    const bsModal = bootstrap.Modal.getInstance(modal);
                    if (bsModal) {
                        bsModal.hide();
                    }
                }
                

                if (result.reload !== false) {
                    setTimeout(() => window.location.reload(), 1000);
                }
            } else {
                this.showToast(result.error || 'Произошла ошибка', 'error');
            }
        } catch (error) {
            console.error('AJAX form error:', error);
            this.showToast('Ошибка при выполнении операции', 'error');
        } finally {
            this.hideLoading(button);
        }
    }
    
    async handleAjaxButton(button) {
        const url = button.dataset.url;
        const method = button.dataset.method || 'POST';
        const confirm = button.dataset.confirm;
        
        if (confirm && !window.confirm(confirm)) {
            return;
        }
        
        try {
            this.showLoading(button);
            
            const response = await fetch(url, { method });
            const result = await response.json();
            
            if (result.success) {
                this.showToast(result.message || 'Операция выполнена успешно', 'success');
                

                if (result.appeal_id && result.status) {
                    this.updateAppealStatusInTable(result.appeal_id, result.status);
                }
                

                if (result.reload !== false) {
                    setTimeout(() => window.location.reload(), 1000);
                }
            } else {
                this.showToast(result.error || 'Произошла ошибка', 'error');
            }
        } catch (error) {
            console.error('AJAX button error:', error);
            this.showToast('Ошибка при выполнении операции', 'error');
        } finally {
            this.hideLoading(button);
        }
    }
    
    updateAppealStatusInTable(appealId, status) {
        const row = document.querySelector(`tr[data-appeal-id="${appealId}"]`);
        if (row) {
            const badge = row.querySelector('.badge');
            if (badge) {
                badge.className = `badge bg-${this.getStatusColor(status)}`;
                badge.textContent = this.getStatusText(status);
            }
        }
    }
    
    getStatusColor(status) {
        const colors = {
            'new': 'warning',
            'received': 'info',
            'done': 'success',
            'declined': 'danger'
        };
        return colors[status] || 'secondary';
    }
    
    getStatusText(status) {
        const texts = {
            'new': 'Новое',
            'received': 'В работе',
            'done': 'Выполнено',
            'declined': 'Отклонено'
        };
        return texts[status] || status;
    }
    
    showLoading(element) {
        if (!element) return;
        
        element.disabled = true;
        element.classList.add('loading');
        
        const originalText = element.textContent || element.innerHTML;
        element.dataset.originalContent = originalText;
        element.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Загрузка...';
    }
    
    hideLoading(element) {
        if (!element) return;
        
        element.disabled = false;
        element.classList.remove('loading');
        
        if (element.dataset.originalContent) {
            element.innerHTML = element.dataset.originalContent;
            delete element.dataset.originalContent;
        }
    }
    
    showToast(message, type = 'info') {
        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            const toastContainer = this.getOrCreateToastContainer();
            
            const toast = document.createElement('div');
            toast.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0`;
            toast.setAttribute('role', 'alert');
            
            toast.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas fa-${this.getToastIcon(type)} me-2"></i>
                        ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            `;
            
            toastContainer.appendChild(toast);
            
            const bsToast = new bootstrap.Toast(toast, {
                autohide: true,
                delay: 4000
            });
            
            bsToast.show();
            
            toast.addEventListener('hidden.bs.toast', () => {
                toast.remove();
            });
        } else {
            this.showSimpleAlert(message, type);
        }
    }
    
    showSimpleAlert(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = `
            top: 20px; right: 20px; z-index: 9999; min-width: 300px; max-width: 400px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        `;
        
        alertDiv.innerHTML = `
            <i class="fas fa-${this.getToastIcon(type)} me-2"></i>
            ${message}
            <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
        `;
        
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            if (alertDiv.parentElement) {
                alertDiv.classList.remove('show');
                setTimeout(() => alertDiv.remove(), 150);
            }
        }, 4000);
    }
    
    getOrCreateToastContainer() {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            document.body.appendChild(container);
        }
        return container;
    }
    
    getToastIcon(type) {
        const icons = {
            'success': 'check-circle',
            'info': 'info-circle',
            'warning': 'exclamation-triangle',
            'error': 'times-circle',
            'danger': 'times-circle'
        };
        return icons[type] || 'info-circle';
    }
    
    updateTimestamps() {
        const timeElements = document.querySelectorAll('[data-timestamp]');
        timeElements.forEach(element => {
            const timestamp = parseInt(element.dataset.timestamp);
            if (timestamp) {
                element.textContent = this.formatRelativeTime(new Date(timestamp * 1000));
            }
        });
    }
    
    formatRelativeTime(date) {
        const now = new Date();
        const diff = now - date;
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days} дн. назад`;
        if (hours > 0) return `${hours} ч. назад`;
        if (minutes > 0) return `${minutes} мин. назад`;
        return 'только что';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.adminPanel = new AdminPanel();
    
    initializeAdditionalFeatures();
});

function initializeAdditionalFeatures() {
    setInterval(updateLiveTime, 1000);
    
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.transform = 'translateY(-2px)';
            card.style.transition = 'transform 0.2s ease';
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.transform = 'translateY(0)';
        });
    });
    
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

function updateLiveTime() {
    const timeElements = document.querySelectorAll('.live-time');
    const now = new Date();
    
    timeElements.forEach(element => {
        const format = element.dataset.format || 'time';
        let timeString = '';
        
        switch (format) {
            case 'time':
                timeString = now.toLocaleTimeString('ru-RU');
                break;
            case 'date':
                timeString = now.toLocaleDateString('ru-RU');
                break;
            case 'datetime':
                timeString = now.toLocaleString('ru-RU');
                break;
        }
        
        element.textContent = timeString;
    });
}

window.showAlert = function(message, type) {
    if (window.adminPanel && window.adminPanel.showToast) {
        window.adminPanel.showToast(message, type);
    } else {
        alert(message);
    }
};

const API = {
    async get(url) {
        const response = await fetch(url, {
            headers: {
                'Accept': 'application/json'
            }
        });
        return response.json();
    },
    
    async post(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async postForm(url, formData) {
        const response = await fetch(url, {
            method: 'POST',
            body: formData
        });
        return response.json();
    }
};

window.API = API;
