/**
 * Expense Tracker - Complete Frontend Application
 * 
 * PURPOSE: Complete frontend logic for expense tracking with OCR processing
 * SCOPE: ~1200 lines - Full application logic with class-based architecture
 * DEPENDENCIES: Modern browser with ES6+, Fetch API, DOM manipulation
 * 
 * AI CONTEXT: This is the complete frontend application logic.
 * Vanilla JavaScript with class-based architecture for maintainability.
 * When working on frontend features, interactions, or UI logic, this is your primary file.
 * 
 * ARCHITECTURE:
 * - ExpenseTrackerApp: Main application class and orchestrator
 * - AppState: Centralized state management
 * - ApiService: Backend communication layer
 * - UI Managers: Specialized classes for different UI components
 * - Event handling: Centralized event delegation and management
 * 
 * FEATURES:
 * - File upload with drag/drop and OCR processing
 * - Real-time form validation and auto-save
 * - Modal-based editing with responsive design
 * - Bulk operations with selection management
 * - Filtering and pagination for large datasets
 * - Error handling and user feedback
 * - Audit trail viewing and management
 * 
 * DEPLOYMENT: Works in both remote VS Code development and Docker production
 * COMPATIBILITY: Modern browsers (Chrome 80+, Firefox 75+, Safari 13+)
 */

'use strict';

// ============================================================================
// APPLICATION STATE MANAGEMENT
// ============================================================================

/**
 * Centralized application state management
 * 
 * AI CONTEXT: Single source of truth for application state.
 * All state changes should go through this class for consistency.
 */
class AppState {
    constructor() {
        this.isUploading = false;
        this.isFormSubmitting = false;
        this.selectedExpenses = new Set();
        this.selectedDrafts = new Set();
        this.currentDeleteOperation = null;
        this.availableCategories = [];
        this.allEntries = [];
        this.allDrafts = [];
        this.pagination = {
            currentPage: 1,
            itemsPerPage: 10,
        };
        this.draftPagination = {
            currentPage: 1,
            itemsPerPage: 10,
        };
    }
    
    setUploadingState(uploading) {
        this.isUploading = uploading;
        const indicator = document.getElementById('status-indicator');
        const text = document.getElementById('status-text');
        
        if (indicator && text) {
            indicator.className = `w-2.5 h-2.5 rounded-full animate-pulse ${uploading ? 'bg-orange-400' : 'bg-green-400'}`;
            text.textContent = uploading ? 'Processing...' : 'Ready';
        }
    }
    
    clearSelections() {
        this.selectedExpenses.clear();
        this.selectedDrafts.clear();
    }
}

// ============================================================================
// API SERVICE LAYER
// ============================================================================

/**
 * Backend API communication service
 * 
 * AI CONTEXT: Centralized API communication with error handling.
 * All backend requests should go through this service.
 */
class ApiService {
    constructor() {
        this.baseUrl = './';
    }
    
    async _fetch(url, options = {}) {
        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    ...options.headers,
                }
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                let detail = errorText;
                try {
                    const errorJson = JSON.parse(errorText);
                    detail = errorJson.detail || errorText;
                } catch (e) {
                    // Use original error text if JSON parsing fails
                }
                throw new Error(`Request failed: ${response.status} - ${detail}`);
            }
            return response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    // Image Upload
    uploadImages(files) {
        const formData = new FormData();
        files.forEach(file => formData.append('files', file));
        return this._fetch(`${this.baseUrl}upload-images`, { method: 'POST', body: formData });
    }

    // Drafts API
    getDrafts() { return this._fetch(`${this.baseUrl}drafts`); }
    getDraft(draftId) { return this._fetch(`${this.baseUrl}drafts/${draftId}`); }
    updateDraft(draftId, formData) {
        return this._fetch(`${this.baseUrl}drafts/${draftId}`, { method: 'PUT', body: formData });
    }
    deleteDraft(draftId) { return this._fetch(`${this.baseUrl}drafts/${draftId}`, { method: 'DELETE' }); }
    confirmDraft(draftId, formData) {
        return this._fetch(`${this.baseUrl}drafts/${draftId}/confirm`, { method: 'POST', body: formData });
    }
    bulkConfirmDrafts(draftIds) {
        const formData = new FormData();
        draftIds.forEach(id => formData.append('draft_ids', id));
        return this._fetch(`${this.baseUrl}drafts/bulk-confirm`, { method: 'POST', body: formData });
    }
    clearDraftError(draftId) {
        return this._fetch(`${this.baseUrl}drafts/${draftId}/clear-error`, { method: 'POST' });
    }

    // Expenses API
    getExpenses() { return this._fetch(`${this.baseUrl}expenses`); }
    getExpense(expenseId) { return this._fetch(`${this.baseUrl}expense/${expenseId}`); }
    updateExpense(expenseId, formData) {
        return this._fetch(`${this.baseUrl}expense/${expenseId}`, { method: 'PUT', body: formData });
    }
    deleteExpense(expenseId) {
        return this._fetch(`${this.baseUrl}expense/${expenseId}`, { method: 'DELETE' });
    }
    bulkDeleteExpenses(expenseIds) {
        const formData = new FormData();
        expenseIds.forEach(id => formData.append('expense_ids', id));
        return this._fetch(`${this.baseUrl}expenses/bulk`, { method: 'DELETE', body: formData });
    }

    // Categories API
    getCategories() { return this._fetch(`${this.baseUrl}categories`); }
    addCategory(name) {
        const formData = new FormData();
        formData.append('name', name);
        return this._fetch(`${this.baseUrl}add-category`, { method: 'POST', body: formData });
    }

    // Utility API
    getFxRate(currency, date = null) {
        const url = date ? `${this.baseUrl}fx-rate/${currency}?date=${date}` : `${this.baseUrl}fx-rate/${currency}`;
        return this._fetch(url);
    }

    getExpenseAuditHistory(expenseId) {
        return this._fetch(`${this.baseUrl}expense/${expenseId}/audit`);
    }
}

// ============================================================================
// NOTIFICATION SYSTEM
// ============================================================================

/**
 * User notification and feedback system
 * 
 * AI CONTEXT: Centralized user feedback with different notification types.
 * Use this for all user communication (success, error, warning, info).
 */
class NotificationManager {
    showNotification(icon, message, type = 'info') {
        const el = document.getElementById('notification');
        const iconEl = document.getElementById('notification-icon');
        const messageEl = document.getElementById('notification-message');
        
        if (!el || !iconEl || !messageEl) return;
        
        iconEl.textContent = icon;
        messageEl.textContent = message;
        
        // Color coding based on type
        const notificationDiv = el.querySelector('div');
        notificationDiv.className = 'bg-white border rounded-lg shadow-lg p-4 min-w-[300px] flex items-center';
        
        // Reset classes
        messageEl.className = 'text-sm font-medium';
        
        if (type === 'error') {
            notificationDiv.classList.add('border-red-200', 'bg-red-50');
            messageEl.classList.add('text-red-800');
        } else if (type === 'success') {
            notificationDiv.classList.add('border-green-200', 'bg-green-50');
            messageEl.classList.add('text-green-800');
        } else if (type === 'warning') {
            notificationDiv.classList.add('border-yellow-200', 'bg-yellow-50');
            messageEl.classList.add('text-yellow-800');
        } else {
            messageEl.classList.add('text-gray-800');
        }
        
        el.classList.remove('hidden');
        setTimeout(() => {
            if (el) el.classList.add('hidden');
        }, 5000);
    }
}

// ============================================================================
// MODAL AND UI MANAGEMENT
// ============================================================================

/**
 * Modal management with ESC key handling
 * 
 * AI CONTEXT: Centralized modal system with proper cleanup and keyboard navigation.
 */
class ModalManager {
    constructor() {
        this.activeModals = [];
        this.setupGlobalEventListeners();
    }
    
    setupGlobalEventListeners() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.handleEscapeKey();
            }
        });
    }
    
    registerModal(modalId, closeFunction) {
        this.activeModals.push({ modalId, closeFunction });
    }
    
    unregisterModal(modalId) {
        this.activeModals = this.activeModals.filter(modal => modal.modalId !== modalId);
    }
    
    handleEscapeKey() {
        if (this.activeModals.length > 0) {
            const lastModal = this.activeModals[this.activeModals.length - 1];
            lastModal.closeFunction();
        }
    }
    
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('active');
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    }
    
    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('active');
            modal.classList.add('hidden');
            document.body.style.overflow = '';
        }
    }
}

// ============================================================================
// FILE UPLOAD AND OCR PROCESSING
// ============================================================================

/**
 * File upload manager with drag/drop support
 * 
 * AI CONTEXT: Handles file upload workflow and OCR processing initiation.
 * Supports drag/drop, multiple files, and progress feedback.
 */
class FileUploadManager {
    constructor(apiService, notificationManager, appState) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.appState = appState;
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        const uploadArea = document.getElementById('upload-area');
        const fileInputBtn = document.getElementById('file-input-btn');
        const fileInput = document.getElementById('file-input');
        
        if (fileInputBtn && fileInput) {
            fileInputBtn.addEventListener('click', () => fileInput.click());
        }
        
        if (uploadArea) {
            uploadArea.addEventListener('dragover', this.handleDragOver.bind(this));
            uploadArea.addEventListener('dragleave', this.handleDragLeave.bind(this));
            uploadArea.addEventListener('drop', this.handleDrop.bind(this));
        }
        
        if (fileInput) {
            fileInput.addEventListener('change', this.handleFileSelect.bind(this));
        }
    }
    
    handleDragOver(e) {
        e.preventDefault();
        e.currentTarget.classList.add('border-blue-400', 'bg-blue-50');
    }
    
    handleDragLeave(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('border-blue-400', 'bg-blue-50');
    }
    
    handleDrop(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('border-blue-400', 'bg-blue-50');
        this.processFiles(Array.from(e.dataTransfer.files));
    }
    
    handleFileSelect(e) {
        this.processFiles(Array.from(e.target.files));
        e.target.value = ''; // Reset input
    }
    
    async processFiles(files) {
        if (this.appState.isUploading) return;
        
        const imageFiles = files.filter(f => f.type.startsWith('image/'));
        if (imageFiles.length === 0) {
            this.notificationManager.showNotification('⚠️', 'Please select one or more image files.', 'warning');
            return;
        }

        this.appState.setUploadingState(true);
        
        try {
            const data = await this.apiService.uploadImages(imageFiles);
            if (data.drafts_created > 0) {
                this.notificationManager.showNotification('✅', `${data.drafts_created} draft(s) created and ready for review.`, 'success');
                // Trigger draft reload
                window.expenseTracker.loadDrafts();
            } else {
                this.notificationManager.showNotification('❌', 'Could not extract any data from the uploaded image(s).', 'error');
            }
        } catch (error) { 
            console.error('Upload error:', error);
            this.notificationManager.showNotification('❌', `Failed to process images: ${error.message}`, 'error'); 
        } finally { 
            this.appState.setUploadingState(false); 
        }
    }
}

// ============================================================================
// FORM MANAGEMENT AND VALIDATION
// ============================================================================

/**
 * Form validation and management
 * 
 * AI CONTEXT: Real-time form validation with visual feedback.
 * Handles both client-side validation and server-side error display.
 */
class FormManager {
    constructor(notificationManager) {
        this.notificationManager = notificationManager;
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // Real-time validation
        const amountInput = document.getElementById('amount');
        const descriptionInput = document.getElementById('description');
        
        if (amountInput) {
            amountInput.addEventListener('input', (e) => this.validateField(e.target, 'amount'));
        }
        if (descriptionInput) {
            descriptionInput.addEventListener('input', (e) => this.validateField(e.target, 'description'));
        }
    }
    
    validateField(element, fieldName) {
        const errorDiv = document.getElementById(`${fieldName}-error`);
        let isValid = true;
        
        if (fieldName === 'amount') {
            isValid = parseFloat(element.value) > 0;
        } else if (fieldName === 'description') {
            isValid = element.value.trim().length > 0;
        }
        
        element.classList.toggle('error-state', !isValid);
        if (errorDiv) {
            errorDiv.classList.toggle('hidden', isValid);
        }
    }
    
    validateForm() {
        let isValid = true;
        const errors = [];
        
        // Clear previous error states
        document.querySelectorAll('.error-state').forEach(el => el.classList.remove('error-state'));
        document.querySelectorAll('.error-message').forEach(el => el.classList.add('hidden'));
        
        // Validate required fields
        const fields = [
            { id: 'amount', name: 'Amount', validator: (val) => parseFloat(val) > 0 },
            { id: 'description', name: 'Description', validator: (val) => val.trim().length > 0 },
            { id: 'selected-category', name: 'Category', validator: (val) => val.trim().length > 0 },
        ];
        
        // Validate person selection
        const personSelected = document.querySelector('input[name="person"]:checked');
        if (!personSelected) {
            fields.push({ id: 'person-error', name: 'Person', validator: () => false });
        }
        
        fields.forEach(field => {
            const element = document.getElementById(field.id);
            if (element) {
                const value = element.value || '';
                const isFieldValid = field.validator(value);
                
                if (!isFieldValid) {
                    element.classList.add('error-state');
                    const errorDiv = document.getElementById(`${field.id.replace('selected-', '')}-error`);
                    if (errorDiv) {
                        errorDiv.classList.remove('hidden');
                    }
                    errors.push(`${field.name} is required`);
                    isValid = false;
                }
            }
        });
        
        return { isValid, errors };
    }
    
    getFormData() {
        const form = document.getElementById('expense-form');
        if (!form) return null;
        
        const formData = new FormData(form);
        
        // Add selected category
        const selectedCategory = document.getElementById('selected-category');
        if (selectedCategory && selectedCategory.value) {
            formData.set('category', selectedCategory.value);
        }
        
        // Add selected person
        const selectedPerson = document.querySelector('input[name="person"]:checked');
        if (selectedPerson) {
            formData.set('person', selectedPerson.value);
        }
        
        // Add selected beneficiary (optional)
        const selectedBeneficiary = document.querySelector('input[name="beneficiary"]:checked');
        if (selectedBeneficiary) {
            formData.set('beneficiary', selectedBeneficiary.value);
        }
        
        return formData;
    }
}

// ============================================================================
// EXPENSE AND DRAFT MANAGERS
// ============================================================================

/**
 * Draft management with auto-save and error handling
 * 
 * AI CONTEXT: Manages OCR processing results before confirmation.
 * Supports auto-save, bulk operations, and error state management.
 */
class DraftManager {
    constructor(apiService, notificationManager, appState) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.appState = appState;
        this.filteredDrafts = [];
        this.autoSaveTimeout = null;
        this.currentEditingDraftId = null;
    }
    
    async loadDrafts() {
        const loadingIndicator = document.getElementById('drafts-loading');
        if (loadingIndicator) {
            loadingIndicator.classList.remove('hidden');
        }
        
        try {
            this.appState.allDrafts = await this.apiService.getDrafts();
            this.filteredDrafts = [...this.appState.allDrafts];
            this.renderDrafts();
            this.updateVisibility();
        } catch (error) {
            console.error('Failed to load drafts:', error);
            this.notificationManager.showNotification('❌', `Failed to load drafts: ${error.message}`, 'error');
        } finally {
            if (loadingIndicator) {
                loadingIndicator.classList.add('hidden');
            }
        }
    }
    
    renderDrafts() {
        const list = document.getElementById('drafts-list');
        const section = document.getElementById('drafts-section');
        
        if (!list || !section) return;
        
        if (this.filteredDrafts.length === 0) {
            section.classList.add('hidden');
            return;
        }
        
        section.classList.remove('hidden');
        
        const { currentPage, itemsPerPage } = this.appState.draftPagination;
        const start = (currentPage - 1) * itemsPerPage;
        const end = start + itemsPerPage;
        const pageDrafts = this.filteredDrafts.slice(start, end);
        
        list.innerHTML = pageDrafts.map(draft => this.renderDraftItem(draft)).join('');
        this.updateBulkActions();
    }
    
    renderDraftItem(draft) {
        const description = draft.description || 'Untitled Draft';
        const amount = draft.amount ? `${parseFloat(draft.amount).toFixed(2)} ${draft.currency || 'EUR'}` : 'No amount';
        const isSelected = this.appState.selectedDrafts.has(draft.id);
        const hasError = draft.has_error;
        const errorClass = hasError ? 'has-error' : '';
        
        let errorIndicatorHtml = '';
        let clearErrorBtnHtml = '';
        if (hasError) {
            errorIndicatorHtml = `<span class="error-indicator" title="${draft.error_message || 'Unknown error'}">⚠️</span>`;
            clearErrorBtnHtml = `<button class="clear-error-btn" onclick="window.expenseTracker.clearDraftError(${draft.id})" title="Clear error and try again">Clear Error</button>`;
        }
        
        return `
            <div class="item-row ${isSelected ? 'selected' : ''} ${errorClass}" data-draft-id="${draft.id}" onclick="window.expenseTracker.handleDraftRowClick(event, ${draft.id})">
                <div class="item-selector" onclick="event.stopPropagation(); window.expenseTracker.toggleDraftSelection(${draft.id})">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
                </div>
                <div class="flex items-center gap-3 cursor-pointer">
                    <div class="flex-1">
                        <p class="font-medium text-gray-900 text-sm flex items-center">
                            ${description}
                            ${errorIndicatorHtml}
                        </p>
                        <div class="flex items-center flex-wrap gap-x-2 gap-y-1 text-xs text-gray-600 mt-1">
                            <span class="font-semibold text-yellow-700">${amount}</span>
                            <span>📅 ${draft.date || 'N/A'}</span>
                            ${draft.has_image ? '<span title="Image attached">📷</span>' : '<span>📄</span>'}
                            ${hasError ? `<span class="text-red-600" title="${draft.error_message}">⚠️ Needs attention</span>` : ''}
                        </div>
                    </div>
                    <div class="item-actions" onclick="event.stopPropagation()">
                        ${hasError ? clearErrorBtnHtml : ''}
                        <button class="action-btn confirm" onclick="window.expenseTracker.editDraft(${draft.id})" ${hasError ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : ''}>✅ Confirm</button>
                        <button class="action-btn delete" onclick="window.expenseTracker.deleteDraft(${draft.id})">🗑️ Dismiss</button>
                    </div>
                </div>
            </div>`;
    }
    
    updateBulkActions() {
        const bulkActions = document.getElementById('draft-bulk-actions');
        const selectedCount = document.getElementById('draft-selected-count');
        const toggleBtn = document.getElementById('draft-toggle-select-btn');
        
        if (!bulkActions || !selectedCount || !toggleBtn) return;
        
        const count = this.appState.selectedDrafts.size;
        const totalVisible = document.querySelectorAll('#drafts-list .item-row').length;
        const allSelected = count === totalVisible && totalVisible > 0;
        
        selectedCount.textContent = `${count} selected`;
        toggleBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        toggleBtn.className = `bulk-btn ${allSelected ? 'deselect-all' : 'select-all'}`;
        
        bulkActions.classList.toggle('show', count > 0);
    }
    
    updateVisibility() {
        const section = document.getElementById('drafts-section');
        if (section) {
            section.classList.toggle('hidden', this.filteredDrafts.length === 0);
        }
    }
    
    async clearDraftError(draftId) {
        try {
            await this.apiService.clearDraftError(draftId);
            this.notificationManager.showNotification('✅', 'Error cleared successfully', 'success');
            await this.loadDrafts();
        } catch (error) {
            console.error(`Failed to clear error for draft ${draftId}:`, error);
            this.notificationManager.showNotification('❌', `Could not clear error: ${error.message}`, 'error');
        }
    }
}

/**
 * Expense list management
 * 
 * AI CONTEXT: Manages confirmed expense display and operations.
 * Handles the "Last 5" view and interfaces with bulk operations.
 */
class ExpenseManager {
    constructor(apiService, notificationManager, appState) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.appState = appState;
    }
    
    async loadExpenses() {
        const loadingIndicator = document.getElementById('expenses-loading');
        if (loadingIndicator) {
            loadingIndicator.classList.remove('hidden');
        }
        
        try {
            this.appState.allEntries = await this.apiService.getExpenses();
            this.renderLastFive();
        } catch (error) { 
            console.error('Failed to load expenses:', error);
            this.notificationManager.showNotification('❌', `Failed to load expenses: ${error.message}`, 'error');
            const list = document.getElementById('expenses-list');
            if (list) {
                list.innerHTML = `<div class="text-center py-10"><p class="text-red-500">Failed to load entries. Please refresh.</p></div>`;
            }
        } finally {
            if (loadingIndicator) {
                loadingIndicator.classList.add('hidden');
            }
        }
    }

    renderLastFive() {
        const list = document.getElementById('expenses-list');
        if (!list) return;
        
        const { allEntries } = this.appState;
        
        if (allEntries.length === 0) {
            list.innerHTML = '<div class="text-center py-10"><p class="text-gray-500">No expenses recorded yet.</p><p class="text-sm text-gray-400 mt-2">Upload a receipt to get started!</p></div>';
            return;
        }
        
        const lastFive = allEntries.slice(0, 5);
        list.innerHTML = lastFive.map(exp => this.renderExpenseItem(exp)).join('');
        this.updateBulkActions();
    }

    renderExpenseItem(exp) {
        const isSelected = this.appState.selectedExpenses.has(exp.id);
        return `
            <div class="item-row ${isSelected ? 'selected' : ''}" data-expense-id="${exp.id}" onclick="window.expenseTracker.handleExpenseRowClick(event, ${exp.id})">
                <div class="item-selector" onclick="event.stopPropagation(); window.expenseTracker.toggleExpenseSelection(${exp.id})">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
                </div>
                <div class="flex items-center gap-3">
                    <div class="flex-1">
                        <p class="font-medium text-gray-900 text-sm">${exp.description || 'No description'}</p>
                        <div class="flex items-center flex-wrap gap-x-2 gap-y-1 text-xs text-gray-600 mt-1">
                            <span class="font-semibold text-blue-700">${parseFloat(exp.amount).toFixed(2)} ${exp.currency}</span>
                            ${exp.currency !== 'EUR' ? `<span class="text-gray-500">(€${parseFloat(exp.amount_eur).toFixed(2)})</span>` : ''}
                            <span class="bg-gray-100 px-1.5 py-0.5 rounded-full">${exp.category}</span>
                            <span>📅 ${exp.date}</span>
                            <span>👤 ${exp.person}</span>
                            ${exp.beneficiary ? `<span>🎯 ${exp.beneficiary}</span>` : ''}
                            ${exp.has_image ? '<span title="Image attached">📷</span>' : ''}
                        </div>
                    </div>
                    <div class="expense-actions item-actions" onclick="event.stopPropagation()">
                        <button class="action-btn edit" onclick="window.expenseTracker.editExpense(${exp.id})">✏️ Edit</button>
                        <button class="action-btn history" onclick="window.expenseTracker.showAuditHistory(${exp.id})">📋 History</button>
                        <button class="action-btn delete" onclick="window.expenseTracker.deleteExpense(${exp.id})">🗑️ Delete</button>
                    </div>
                </div>
            </div>`;
    }
    
    updateBulkActions() {
        const bulkActions = document.getElementById('last5-bulk-actions');
        const selectedCount = document.getElementById('last5-selected-count');
        const toggleBtn = document.getElementById('last5-toggle-select-btn');
        
        if (!bulkActions || !selectedCount || !toggleBtn) return;
        
        const count = this.appState.selectedExpenses.size;
        const totalVisible = document.querySelectorAll('#expenses-list .item-row').length;
        const allSelected = count === totalVisible && totalVisible > 0;
        
        selectedCount.textContent = `${count} selected`;
        toggleBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        toggleBtn.className = `bulk-btn ${allSelected ? 'deselect-all' : 'select-all'}`;
        
        bulkActions.classList.toggle('show', count > 0);
    }
}

// ============================================================================
// MAIN APPLICATION CLASS
// ============================================================================

/**
 * Main expense tracker application
 * 
 * AI CONTEXT: Central orchestrator for the entire application.
 * This is the main entry point and coordinates all other components.
 */
class ExpenseTrackerApp {
    constructor() {
        this.appState = new AppState();
        this.apiService = new ApiService();
        this.notificationManager = new NotificationManager();
        this.modalManager = new ModalManager();
        this.formManager = new FormManager(this.notificationManager);
        this.fileUploadManager = new FileUploadManager(this.apiService, this.notificationManager, this.appState);
        this.draftManager = new DraftManager(this.apiService, this.notificationManager, this.appState);
        this.expenseManager = new ExpenseManager(this.apiService, this.notificationManager, this.appState);
        
        this.availableCategories = [];
        this.initialize();
    }
    
    async initialize() {
        try {
            await Promise.all([
                this.loadCategories(),
                this.expenseManager.loadExpenses(),
                this.draftManager.loadDrafts()
            ]);
            
            this.setupEventListeners();
            this.setDefaultFormDate();
            
            console.log('✅ Expense Tracker initialized successfully');
        } catch (error) {
            console.error('❌ Failed to initialize Expense Tracker:', error);
            this.notificationManager.showNotification('❌', 'Failed to initialize application', 'error');
        }
    }
    
    setupEventListeners() {
        // Bulk action handlers
        const draftToggleBtn = document.getElementById('draft-toggle-select-btn');
        if (draftToggleBtn) {
            draftToggleBtn.addEventListener('click', () => this.toggleDraftSelectAll());
        }
        
        const last5ToggleBtn = document.getElementById('last5-toggle-select-btn');
        if (last5ToggleBtn) {
            last5ToggleBtn.addEventListener('click', () => this.toggleExpenseSelectAll());
        }
        
        // Form submission
        const expenseForm = document.getElementById('expense-form');
        if (expenseForm) {
            expenseForm.addEventListener('submit', (e) => this.handleFormSubmit(e));
        }
        
        // Modal close handlers
        const editModalClose = document.querySelector('.edit-modal-close');
        if (editModalClose) {
            editModalClose.addEventListener('click', () => this.hideEditModal());
        }
        
        // Category management
        const addCategoryBtn = document.getElementById('add-category-btn');
        if (addCategoryBtn) {
            addCategoryBtn.addEventListener('click', () => this.showAddCategoryModal());
        }
    }
    
    // ============================================================================
    // CATEGORY MANAGEMENT
    // ============================================================================
    
    async loadCategories() {
        try {
            this.availableCategories = await this.apiService.getCategories();
            this.renderCategoryButtons();
            return this.availableCategories;
        } catch (error) { 
            console.error('Failed to load categories:', error);
            this.notificationManager.showNotification('❌', 'Failed to load categories', 'error');
            return [];
        }
    }
    
    renderCategoryButtons() {
        const container = document.getElementById('category-buttons');
        if (!container) return;
        
        container.innerHTML = '';
        
        this.availableCategories.forEach(cat => {
            const segment = document.createElement('div');
            segment.className = 'category-segment';
            segment.innerHTML = `
                <div class="category-slider"></div>
                <label>
                    <input type="radio" name="category" value="${cat}">
                    <span class="category-option">${cat}</span>
                </label>
            `;
            
            const input = segment.querySelector('input');
            input.addEventListener('click', (e) => this.handleCategoryClick(e, cat));
            
            container.appendChild(segment);
        });
    }
    
    handleCategoryClick(event, categoryName) {
        const input = event.target;
        
        if (input.checked && input.dataset.wasChecked === 'true') {
            input.checked = false;
            input.dataset.wasChecked = 'false';
            document.getElementById('selected-category').value = '';
        } else {
            document.querySelectorAll('.category-segment input[type="radio"]').forEach(radio => {
                radio.checked = false;
                radio.dataset.wasChecked = 'false';
            });
            
            input.checked = true;
            input.dataset.wasChecked = 'true';
            document.getElementById('selected-category').value = categoryName;
        }
        
        // Clear validation error if category selected
        if (categoryName) {
            const categoryError = document.getElementById('category-error');
            if (categoryError) {
                categoryError.classList.add('hidden');
            }
        }
    }
    
    // ============================================================================
    // DRAFT OPERATIONS
    // ============================================================================
    
    async loadDrafts() {
        await this.draftManager.loadDrafts();
    }
    
    handleDraftRowClick(event, draftId) {
        if (!event.target.closest('.item-actions') && !event.target.closest('.item-selector')) {
            this.editDraft(draftId);
        }
    }
    
    toggleDraftSelection(draftId) {
        const item = document.querySelector(`[data-draft-id="${draftId}"]`);
        if (!item) return;

        const isSelected = item.classList.toggle('selected');
        
        if (isSelected) {
            this.appState.selectedDrafts.add(draftId);
        } else {
            this.appState.selectedDrafts.delete(draftId);
        }
        this.draftManager.updateBulkActions();
    }
    
    toggleDraftSelectAll() {
        const totalVisible = document.querySelectorAll('#drafts-list .item-row').length;
        const allSelected = this.appState.selectedDrafts.size === totalVisible && totalVisible > 0;
        
        if (allSelected) {
            this.clearDraftSelection();
        } else {
            this.selectAllVisibleDrafts();
        }
    }
    
    selectAllVisibleDrafts() {
        document.querySelectorAll('#drafts-list .item-row').forEach(item => {
            const draftId = parseInt(item.dataset.draftId);
            if (!this.appState.selectedDrafts.has(draftId)) {
                item.classList.add('selected');
                this.appState.selectedDrafts.add(draftId);
            }
        });
        this.draftManager.updateBulkActions();
    }
    
    clearDraftSelection() {
        document.querySelectorAll('#drafts-list .item-row.selected').forEach(item => {
            item.classList.remove('selected');
        });
        this.appState.selectedDrafts.clear();
        this.draftManager.updateBulkActions();
    }
    
    async editDraft(draftId) {
        try {
            const draftData = await this.apiService.getDraft(draftId);
            this.populateEditForm(draftData, 'draft');
        } catch (error) {
            console.error(`Failed to load draft ${draftId}:`, error);
            this.notificationManager.showNotification('❌', `Could not load draft for editing: ${error.message}`, 'error');
        }
    }
    
    async deleteDraft(draftId) {
        if (confirm('Are you sure you want to dismiss this draft?')) {
            try {
                await this.apiService.deleteDraft(draftId);
                this.notificationManager.showNotification('🗑️', 'Draft dismissed.', 'success');
                await this.loadDrafts();
            } catch (error) {
                console.error(`Failed to dismiss draft ${draftId}:`, error);
                this.notificationManager.showNotification('❌', `Could not dismiss draft: ${error.message}`, 'error');
            }
        }
    }
    
    async clearDraftError(draftId) {
        await this.draftManager.clearDraftError(draftId);
    }
    
    // ============================================================================
    // EXPENSE OPERATIONS
    // ============================================================================
    
    handleExpenseRowClick(event, expenseId) {
        if (!event.target.closest('.item-actions') && !event.target.closest('.item-selector')) {
            this.editExpense(expenseId);
        }
    }
    
    toggleExpenseSelection(expenseId) {
        const item = document.querySelector(`[data-expense-id="${expenseId}"]`);
        if (!item) return;

        const isSelected = item.classList.toggle('selected');
        
        if (isSelected) {
            this.appState.selectedExpenses.add(expenseId);
        } else {
            this.appState.selectedExpenses.delete(expenseId);
        }
        this.expenseManager.updateBulkActions();
    }
    
    toggleExpenseSelectAll() {
        const totalVisible = document.querySelectorAll('#expenses-list .item-row').length;
        const allSelected = this.appState.selectedExpenses.size === totalVisible && totalVisible > 0;
        
        if (allSelected) {
            this.clearExpenseSelection();
        } else {
            this.selectAllVisibleExpenses();
        }
    }
    
    selectAllVisibleExpenses() {
        document.querySelectorAll('#expenses-list .item-row').forEach(item => {
            const expenseId = parseInt(item.dataset.expenseId);
            if (!this.appState.selectedExpenses.has(expenseId)) {
                item.classList.add('selected');
                this.appState.selectedExpenses.add(expenseId);
            }
        });
        this.expenseManager.updateBulkActions();
    }
    
    clearExpenseSelection() {
        document.querySelectorAll('#expenses-list .item-row.selected').forEach(item => {
            item.classList.remove('selected');
        });
        this.appState.selectedExpenses.clear();
        this.expenseManager.updateBulkActions();
    }
    
    async editExpense(expenseId) {
        try {
            const expense = await this.apiService.getExpense(expenseId);
            this.populateEditForm(expense, 'expense');
        } catch (error) { 
            console.error('Edit expense error:', error);
            this.notificationManager.showNotification('❌', `Could not load expense for editing: ${error.message}`, 'error'); 
        }
    }
    
    async deleteExpense(expenseId) {
        if (confirm('Are you sure you want to delete this expense?')) {
            try {
                await this.apiService.deleteExpense(expenseId);
                this.notificationManager.showNotification('✅', 'Expense deleted successfully!', 'success');
                await this.expenseManager.loadExpenses();
            } catch (error) {
                console.error(`Failed to delete expense ${expenseId}:`, error);
                this.notificationManager.showNotification('❌', `Could not delete expense: ${error.message}`, 'error');
            }
        }
    }
    
    // ============================================================================
    // FORM MANAGEMENT
    // ============================================================================
    
    populateEditForm(data, type = 'expense') {
        this.resetEditForm(false);
        
        // Set form values
        const form = document.getElementById('expense-form');
        if (!form) return;
        
        // Hidden fields
        document.getElementById('expense-id').value = type === 'expense' ? (data.id || '') : '';
        document.getElementById('draft-id').value = type === 'draft' ? (data.id || '') : '';
        
        // Basic fields
        document.getElementById('date').value = data.date || new Date().toISOString().split('T')[0];
        document.getElementById('amount').value = data.amount || '';
        document.getElementById('currency').value = data.currency || 'EUR';
        document.getElementById('description').value = data.description || '';
        document.getElementById('fx-rate').value = data.fx_rate || 1.0;
        document.getElementById('amount-eur').value = data.amount_eur || 0;
        
        // Set category
        this.setSelectedCategory(data.category || 'Other');
        
        // Set person
        this.setPersonSelection(data.person || 'Közös');
        
        // Set beneficiary (optional)
        if (data.beneficiary) {
            this.setBeneficiarySelection(data.beneficiary);
        }
        
        // Update modal title
        this.updateModalTitle(data, type);
        
        // Show modal
        this.showEditModal();
    }
    
    setSelectedCategory(categoryName) {
        // Clear all category selections
        document.querySelectorAll('.category-segment input[type="radio"]').forEach(radio => {
            radio.checked = false;
            radio.dataset.wasChecked = 'false';
        });
        
        // Set the selected category
        const targetInput = document.querySelector(`.category-segment input[value="${categoryName}"]`);
        if (targetInput) {
            targetInput.checked = true;
            targetInput.dataset.wasChecked = 'true';
        }
        document.getElementById('selected-category').value = categoryName;
    }
    
    setPersonSelection(personName) {
        const personRadio = document.querySelector(`input[name="person"][value="${personName}"]`);
        if (personRadio) {
            document.querySelectorAll('input[name="person"]').forEach(r => r.checked = false);
            personRadio.checked = true;
        }
    }
    
    setBeneficiarySelection(beneficiaryName) {
        const beneficiaryRadio = document.querySelector(`input[name="beneficiary"][value="${beneficiaryName}"]`);
        if (beneficiaryRadio) {
            document.querySelectorAll('input[name="beneficiary"]').forEach(r => r.checked = false);
            beneficiaryRadio.checked = true;
        }
    }
    
    updateModalTitle(data, type) {
        const modalTitleText = document.getElementById('modal-title-text');
        const saveBtnText = document.getElementById('modal-save-btn-text');
        
        if (modalTitleText && saveBtnText) {
            if (type === 'expense') {
                modalTitleText.innerHTML = `<span class="w-2 h-2 bg-orange-500 rounded-full mr-3"></span>Edit Expense #${data.id}`;
                saveBtnText.textContent = '💾 Update';
            } else {
                modalTitleText.innerHTML = `<span class="w-2 h-2 bg-blue-500 rounded-full mr-3"></span>Confirm New Expense Draft`;
                saveBtnText.textContent = '💾 Save Expense';
            }
        }
    }
    
    resetEditForm(hide = true) {
        const form = document.getElementById('expense-form');
        if (form) {
            form.reset();
        }
        
        // Clear validation states
        document.querySelectorAll('.error-state').forEach(el => el.classList.remove('error-state'));
        document.querySelectorAll('.error-message').forEach(el => el.classList.add('hidden'));
        
        // Reset category selection
        document.querySelectorAll('.category-segment input[type="radio"]').forEach(radio => {
            radio.checked = false;
            radio.dataset.wasChecked = 'false';
        });
        document.getElementById('selected-category').value = '';
        
        // Set default date
        this.setDefaultFormDate();
        
        if (hide) {
            this.hideEditModal();
        }
    }
    
    setDefaultFormDate() {
        const dateInput = document.getElementById('date');
        if (dateInput) {
            dateInput.value = new Date().toISOString().split('T')[0];
        }
    }
    
    showEditModal() {
        this.renderEditFormContent();
        this.modalManager.showModal('edit-modal');
        this.modalManager.registerModal('edit-modal', () => this.hideEditModal());
    }
    
    hideEditModal() {
        this.modalManager.hideModal('edit-modal');
        this.modalManager.unregisterModal('edit-modal');
    }
    
    renderEditFormContent() {
        const formContent = document.getElementById('form-content');
        if (!formContent) return;
        
        formContent.innerHTML = `
            <div class="three-column-section">
                <div class="form-group">
                    <div>
                        <label for="date" class="form-label">Date <span class="text-red-500">*</span></label>
                        <input type="date" id="date" name="date" required class="form-input">
                        <div id="date-error" class="error-message hidden">Please select a valid date</div>
                    </div>
                    <div>
                        <label for="description" class="form-label">Description <span class="text-red-500">*</span></label>
                        <input type="text" id="description" name="description" required class="form-input" placeholder="e.g., Coffee with team" maxlength="100">
                        <div id="description-error" class="error-message hidden">Description is required</div>
                    </div>
                </div>
                
                <div class="form-group">
                    <div>
                        <label for="amount" class="form-label">Amount <span class="text-red-500">*</span></label>
                        <input type="number" id="amount" name="amount" step="0.01" min="0" required class="form-input" placeholder="0.00">
                        <div id="amount-error" class="error-message hidden">Please enter a valid amount</div>
                    </div>
                    <div>
                        <label for="currency" class="form-label">Currency <span class="text-red-500">*</span></label>
                        <select id="currency" name="currency" required class="form-select">
                            <option value="EUR" selected>EUR</option>
                            <option value="HUF">HUF</option>
                            <option value="USD">USD</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-group">
                    <div>
                        <label class="form-label">Receipt</label>
                        <div class="receipt-preview">
                            <div class="receipt-placeholder">
                                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 002 2z"></path>
                                </svg>
                                <div style="font-size: 12px;">Click to view receipt</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="section-divider"></div>
            
            <div class="two-column-section">
                <div class="section-column">
                    <div>
                        <label class="form-label">Category <span style="color: #ef4444;">*</span></label>
                        <div id="category-buttons" class="category-control"></div>
                        <div id="category-error" class="error-message hidden">Please select a category</div>
                        <button type="button" id="add-category-btn" class="mt-3 text-sm text-blue-600 hover:text-blue-700 font-medium">+ Add New Category</button>
                        <input type="hidden" id="selected-category" name="category" required>
                    </div>
                </div>
                
                <div class="section-column">
                    <div class="control-row">
                        <label class="form-label">Who Paid? <span class="text-red-500">*</span></label>
                        <div class="segmented-control" data-group="person">
                            <div class="segmented-slider"></div>
                            <label><input type="radio" name="person" value="Ricsi" required><span class="segmented-option">👤 Ricsi</span></label>
                            <label><input type="radio" name="person" value="Virag" required><span class="segmented-option">👤 Virag</span></label>
                            <label><input type="radio" name="person" value="Közös" required checked><span class="segmented-option">🤝 Közös</span></label>
                        </div>
                        <div id="person-error" class="error-message hidden">Please select who paid</div>
                    </div>
                    
                    <div class="control-row">
                        <label class="form-label">For Whom? <span style="color: #6b7280;">(Optional)</span></label>
                        <div class="segmented-control" data-group="beneficiary">
                            <div class="segmented-slider"></div>
                            <label><input type="radio" name="beneficiary" value="Ricsi"><span class="segmented-option">👤 Ricsi</span></label>
                            <label><input type="radio" name="beneficiary" value="Virag"><span class="segmented-option">👤 Virag</span></label>
                            <label><input type="radio" name="beneficiary" value="Közös"><span class="segmented-option">🤝 Közös</span></label>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Re-render categories
        this.renderCategoryButtons();
        
        // Re-setup category button handler
        const addCategoryBtn = document.getElementById('add-category-btn');
        if (addCategoryBtn) {
            addCategoryBtn.addEventListener('click', () => this.showAddCategoryModal());
        }
    }
    
    async handleFormSubmit(e) {
        e.preventDefault();
        if (this.appState.isFormSubmitting) return;
        
        const validation = this.formManager.validateForm();
        if (!validation.isValid) {
            this.notificationManager.showNotification('⚠️', `Please fix the following errors: ${validation.errors.join(', ')}`, 'error');
            return;
        }
        
        const submitBtn = document.getElementById('modal-save-btn');
        const originalText = submitBtn.innerHTML;
        this.appState.isFormSubmitting = true;
        submitBtn.disabled = true; 
        submitBtn.innerHTML = '<span class="spinner mr-2"></span>Saving...';
        
        const expenseId = document.getElementById('expense-id').value;
        const draftId = document.getElementById('draft-id').value;
        const formData = this.formManager.getFormData();

        try {
            if (expenseId) {
                await this.apiService.updateExpense(expenseId, formData);
                this.notificationManager.showNotification('✅', 'Expense updated successfully!', 'success');
            } else if (draftId) {
                const result = await this.apiService.confirmDraft(draftId, formData);
                if (result.success) {
                    this.notificationManager.showNotification('✅', 'Draft confirmed and saved as expense!', 'success');
                    await this.loadDrafts();
                } else {
                    this.notificationManager.showNotification('⚠️', 'Draft has validation errors and remains for fixing.', 'warning');
                    await this.loadDrafts();
                }
            }
            
            this.resetEditForm(true);
            await this.expenseManager.loadExpenses();

        } catch (error) { 
            console.error('Form submit error:', error);
            this.notificationManager.showNotification('❌', `Failed to save expense: ${error.message}`, 'error'); 
        } finally { 
            this.appState.isFormSubmitting = false;
            submitBtn.disabled = false; 
            submitBtn.innerHTML = originalText; 
        }
    }
    
    // ============================================================================
    // UTILITY METHODS
    // ============================================================================
    
    showAddCategoryModal() {
        const modal = document.getElementById('add-category-modal');
        if (modal) {
            modal.classList.remove('hidden');
            this.modalManager.registerModal('add-category-modal', () => this.hideAddCategoryModal());
        }
    }
    
    hideAddCategoryModal() {
        const modal = document.getElementById('add-category-modal');
        if (modal) {
            modal.classList.add('hidden');
            this.modalManager.unregisterModal('add-category-modal');
        }
    }
    
    async showAuditHistory(expenseId) {
        const modal = document.getElementById('audit-history-modal');
        const loading = document.getElementById('audit-loading');
        const content = document.getElementById('audit-content');
        
        if (!modal || !loading || !content) return;
        
        modal.classList.remove('hidden');
        loading.classList.remove('hidden');
        content.innerHTML = '';
        
        try {
            const response = await this.apiService.getExpenseAuditHistory(expenseId);
            const auditHistory = response.audit_history || [];
            
            if (auditHistory.length === 0) {
                content.innerHTML = `<div class="text-center py-8 text-gray-500"><span class="text-4xl">📋</span><p class="mt-2">No audit history found.</p></div>`;
            } else {
                content.innerHTML = auditHistory.map(entry => this.formatAuditEntry(entry)).join('');
            }
            
        } catch (error) {
            content.innerHTML = `<div class="text-center py-8 text-red-500"><span class="text-4xl">❌</span><p class="mt-2">Failed to load audit history: ${error.message}</p></div>`;
        } finally {
            loading.classList.add('hidden');
        }
        
        // Setup close handler
        const closeBtn = document.getElementById('close-audit-modal');
        if (closeBtn) {
            closeBtn.onclick = () => modal.classList.add('hidden');
        }
    }
    
    formatAuditEntry(entry) {
        const op = entry.operation.toLowerCase();
        const icon = {'insert': '➕', 'update': '✏️', 'delete': '🗑️'}[op] || '📝';
        
        return `
            <div class="audit-entry ${op}">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <span class="text-lg">${icon}</span>
                        <div>
                            <span class="audit-operation ${op}">${entry.operation}</span>
                            <div class="text-sm text-gray-600 mt-1">${new Date(entry.audit_timestamp).toLocaleString()} by ${entry.user_info || 'system'}</div>
                        </div>
                    </div>
                </div>
            </div>`;
    }
}

// ============================================================================
// APPLICATION INITIALIZATION
// ============================================================================

/**
 * Initialize the application when DOM is ready
 * 
 * AI CONTEXT: Application entry point.
 * This creates the global expenseTracker instance used throughout the app.
 */
let expenseTracker;

document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Initializing Expense Tracker...');
    expenseTracker = new ExpenseTrackerApp();
    
    // Make it globally available for onclick handlers
    window.expenseTracker = expenseTracker;
});

// ============================================================================
// AI DEVELOPMENT NOTES
// ============================================================================

/**
 * AI COLLABORATION PATTERNS FOR THIS FILE:
 * 
 * 1. **Adding New Features**:
 *    - Create new manager class for complex features
 *    - Add methods to ExpenseTrackerApp for coordination
 *    - Update initialization in constructor and initialize()
 * 
 * 2. **Modifying UI Behavior**:
 *    - Look for specific manager classes (DraftManager, ExpenseManager)
 *    - Update rendering methods for visual changes
 *    - Modify event handlers for interaction changes
 * 
 * 3. **API Integration**:
 *    - Add new methods to ApiService class
 *    - Update error handling in manager classes
 *    - Consider caching strategies for performance
 * 
 * 4. **Form Enhancements**:
 *    - Extend FormManager for new validation rules
 *    - Update renderEditFormContent() for new fields
 *    - Add real-time validation in setupEventListeners()
 * 
 * 5. **State Management**:
 *    - Add new state properties to AppState class
 *    - Update state-dependent rendering methods
 *    - Consider state persistence for complex workflows
 * 
 * PERFORMANCE CONSIDERATIONS:
 * - Use event delegation for dynamic content
 * - Implement virtual scrolling for large lists
 * - Cache DOM queries in constructor
 * - Debounce user input for API calls
 * 
 * TESTING STRATEGIES:
 * - Mock ApiService for unit testing
 * - Test manager classes independently
 * - Use data attributes for integration testing
 * - Implement error boundary patterns
 * 
 * BROWSER COMPATIBILITY:
 * - ES6+ features used (classes, async/await, destructuring)
 * - Fetch API for HTTP requests
 * - Modern DOM methods (classList, querySelector)
 * - Progressive enhancement approach
 * 
 * SCALABILITY PATTERNS:
 * - Component-based architecture ready for framework migration
 * - Event-driven communication between managers
 * - Separation of concerns (API, UI, State, Business Logic)
 * - Configuration-driven behavior where possible
 */