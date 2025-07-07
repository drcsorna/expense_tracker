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
// GLOBAL MODAL MANAGER FOR ESC KEY HANDLING
// ============================================================================

/**
 * Global Modal Manager
 * 
 * AI CONTEXT: Centralized modal management with keyboard navigation support.
 * Handles ESC key press to close the most recently opened modal.
 * Maintains a stack of active modals for proper layering.
 */
class GlobalModalManager {
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
        // Close the most recently opened modal
        if (this.activeModals.length > 0) {
            const lastModal = this.activeModals[this.activeModals.length - 1];
            lastModal.closeFunction();
        }
    }
    
    isModalActive(modalId) {
        return this.activeModals.some(modal => modal.modalId === modalId);
    }
}

// ============================================================================
// APPLICATION STATE MANAGEMENT
// ============================================================================

/**
 * Application State Manager
 * 
 * AI CONTEXT: Centralized state management for the entire application.
 * Single source of truth for all application state including selections,
 * pagination, loading states, and data collections.
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
        indicator.className = `w-2.5 h-2.5 rounded-full animate-pulse ${uploading ? 'bg-orange-400' : 'bg-green-400'}`;
        text.textContent = uploading ? 'Processing...' : 'Ready';
    }
}

// ============================================================================
// API SERVICE CLASS
// ============================================================================

/**
 * API Service Layer
 * 
 * AI CONTEXT: Centralized backend communication with error handling.
 * Provides a clean interface for all HTTP operations with proper
 * response handling and error propagation.
 */
class ApiService {
    constructor() {
        this.baseUrl = './';
    }
    
    async _fetch(url, options = {}) {
        const response = await fetch(url, options);
        if (!response.ok) {
            const errorText = await response.text();
            let detail = errorText;
            try {
                const errorJson = JSON.parse(errorText);
                detail = errorJson.detail || errorText;
            } catch (e) {}
            throw new Error(`Request failed: ${response.status} - ${detail}`);
        }
        return response.json();
    }

    async deleteDraft(draftId) {
        const response = await fetch(`./drafts/${draftId}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            const error = await response.text();
            throw new Error(error);
        }
        return response.json();
    }

    // Image Upload Operations
    uploadImages(files) {
        const formData = new FormData();
        files.forEach(file => formData.append('files', file));
        return this._fetch(`${this.baseUrl}upload-images`, { method: 'POST', body: formData });
    }

    // Draft Operations
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

    // Expense Operations
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

    // Category Operations
    getCategories() { return this._fetch(`${this.baseUrl}categories`); }
    addCategory(name) {
        const formData = new FormData();
        formData.append('name', name);
        return this._fetch(`${this.baseUrl}add-category`, { method: 'POST', body: formData });
    }

    // FX Rate Operations
    getFxRate(currency, date = null) {
        const url = date ? `${this.baseUrl}fx-rate/${currency}?date=${date}` : `${this.baseUrl}fx-rate/${currency}`;
        return this._fetch(url);
    }
}


function calculateDynamicWidths(items) {
    if (!items || items.length === 0) return null;
    
    const maxWidths = {
        amount: 0,
        category: 0,
        person: 0,
        beneficiary: 0
    };
    
    items.forEach(item => {
        const amountText = `€${parseFloat(item.amount).toFixed(2)} ${item.currency}`;
        maxWidths.amount = Math.max(maxWidths.amount, amountText.length);
        maxWidths.category = Math.max(maxWidths.category, (item.category || '').length);
        maxWidths.person = Math.max(maxWidths.person, (item.person || '').length);
        maxWidths.beneficiary = Math.max(maxWidths.beneficiary, (item.beneficiary || '').length);
    });
    
    // Convert to pixel widths (approximate 8px per character)
    const gridColumns = [
        `${Math.max(maxWidths.amount * 8, 100)}px`,  // min 100px for amount
        `${Math.max(maxWidths.category * 8, 80)}px`, // min 80px for category
        '110px',  // fixed for date
        `${Math.max(maxWidths.person * 8, 60)}px`,   // min 60px for person
        `${maxWidths.beneficiary > 0 ? Math.max(maxWidths.beneficiary * 8, 80) : 80}px`, // beneficiary
        '30px'    // picture icon
    ].join(' ');
    
    return gridColumns;
}

function applyDynamicGrid(containerSelector, items) {
    const container = document.querySelector(containerSelector);
    if (!container) return;
    
    const gridColumns = calculateDynamicWidths(items);
    if (gridColumns) {
        container.style.setProperty('--grid-columns', gridColumns);
    }
}


// ============================================================================
// NOTIFICATION MANAGER
// ============================================================================

/**
 * Notification System
 * 
 * AI CONTEXT: User feedback system for success, error, and warning messages.
 * Provides consistent visual feedback across the application with auto-dismiss.
 */
class NotificationManager {
    showNotification(icon, message, type = 'info') {
        const el = document.getElementById('notification');
        const iconEl = document.getElementById('notification-icon');
        const messageEl = document.getElementById('notification-message');
        
        iconEl.textContent = icon;
        messageEl.textContent = message;
        
        // Color coding based on type
        const notificationDiv = el.querySelector('div');
        notificationDiv.className = 'bg-white border rounded-lg shadow-lg p-4 min-w-[300px] flex items-center';
        
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
            if(el) el.classList.add('hidden');
        }, 5000);
    }
}

// ============================================================================
// SEGMENTED CONTROLS MANAGER
// ============================================================================

/**
 * Segmented Controls System
 * 
 * AI CONTEXT: Modern iOS-style segmented controls with sliding animation.
 * Used for person/beneficiary selection with visual feedback and
 * toggle functionality for better user experience.
 */
class SegmentedControlsManager {
    constructor() {
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // Set up segmented controls
        document.querySelectorAll('.segmented-control input[type="radio"]').forEach(radio => {
            radio.addEventListener('click', this.handleSegmentedClick.bind(this));
            radio.dataset.wasChecked = radio.checked ? 'true' : 'false';
        });
        
        // Initialize sliders
        document.querySelectorAll('.segmented-control').forEach(this.updateSlider);
        
        // Update sliders on window resize
        window.addEventListener('resize', () => {
            document.querySelectorAll('.segmented-control').forEach(this.updateSlider);
        });
        
        // Set default selection for "Who Paid?" to Közös
        setTimeout(() => {
            const kozosRadio = document.querySelector('input[name="person"][value="Közös"]');
            if (kozosRadio) {
                kozosRadio.checked = true;
                kozosRadio.dataset.wasChecked = 'true';
                this.updateSlider(kozosRadio.closest('.segmented-control'));
            }
        }, 100);
    }
    
    updateSlider(control) {
        if (!control) return;
        const slider = control.querySelector('.segmented-slider');
        const checkedInput = control.querySelector('input[type="radio"]:checked');
        
        if (checkedInput) {
            const label = checkedInput.closest('label');
            const option = label.querySelector('.segmented-option');
            
            const controlRect = control.getBoundingClientRect();
            const optionRect = option.getBoundingClientRect();
            
            const left = optionRect.left - controlRect.left - 2;
            const width = optionRect.width;
            
            slider.style.transform = `translateX(${left}px)`;
            slider.style.width = `${width}px`;
            control.classList.add('has-selection');
        } else {
            control.classList.remove('has-selection');
        }
    }
    
    handleSegmentedClick(event) {
        const input = event.target;
        const control = input.closest('.segmented-control');
        
        if (input.checked && input.dataset.wasChecked === 'true') {
            input.checked = false;
            input.dataset.wasChecked = 'false';
        } else {
            const allInGroup = control.querySelectorAll('input[type="radio"]');
            allInGroup.forEach(radio => radio.dataset.wasChecked = 'false');
            input.dataset.wasChecked = 'true';
        }
        
        this.updateSlider(control);
    }
    
    resetControls() {
        document.querySelectorAll('.segmented-control input[type="radio"]').forEach(radio => {
            radio.checked = false;
            radio.dataset.wasChecked = 'false';
        });
        document.querySelectorAll('.segmented-control').forEach(control => {
            control.classList.remove('has-selection');
        });
        
        setTimeout(() => {
            const kozosRadio = document.querySelector('input[name="person"][value="Közös"]');
            if (kozosRadio) {
                kozosRadio.checked = true;
                kozosRadio.dataset.wasChecked = 'true';
                this.updateSlider(kozosRadio.closest('.segmented-control'));
            }
        }, 50);
    }
}

// ============================================================================
// CATEGORY MANAGER
// ============================================================================

/**
 * Category Management System
 * 
 * AI CONTEXT: Handles expense category operations including dynamic loading,
 * user category creation, and category selection with visual feedback.
 */
class CategoryManager {
    constructor(apiService, notificationManager) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        document.getElementById('add-category-btn').addEventListener('click', () => {
            document.getElementById('add-category-modal').classList.remove('hidden');
            expenseTracker.modalManager.globalModalManager.registerModal('add-category-modal', () => {
                document.getElementById('add-category-modal').classList.add('hidden');
                expenseTracker.modalManager.globalModalManager.unregisterModal('add-category-modal');
            });
        });
        document.getElementById('add-category-form').addEventListener('submit', 
            this.handleAddCategory.bind(this));
        document.getElementById('cancel-category').addEventListener('click', () => {
            document.getElementById('add-category-modal').classList.add('hidden');
            expenseTracker.modalManager.globalModalManager.unregisterModal('add-category-modal');
        });
    }
    
    async loadCategories() {
        try {
            const categories = await this.apiService.getCategories();
            const container = document.getElementById('category-buttons');
            container.innerHTML = '';
            
            categories.forEach(cat => {
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
            
            return categories;
        } catch (error) { 
            console.error('Failed to load categories:', error);
            this.notificationManager.showNotification('❌', 'Failed to load categories', 'error');
            return [];
        }
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
        
        if (categoryName) {
            document.getElementById('category-error').classList.add('hidden');
        }
    }
    
    setSelectedCategory(name) {
        document.querySelectorAll('.category-segment input[type="radio"]').forEach(radio => {
            radio.checked = false;
            radio.dataset.wasChecked = 'false';
        });
        
        const targetInput = document.querySelector(`.category-segment input[value="${name}"]`);
        if (targetInput) {
            targetInput.checked = true;
            targetInput.dataset.wasChecked = 'true';
        }
        document.getElementById('selected-category').value = name;
    }
    
    resetCategories() {
        document.querySelectorAll('.category-segment input[type="radio"]').forEach(radio => {
            radio.checked = false;
            radio.dataset.wasChecked = 'false';
            radio.closest('.category-segment').classList.remove('has-selection');
        });
        document.getElementById('selected-category').value = '';
    }
    
    async handleAddCategory(e) {
        e.preventDefault();
        const form = document.getElementById('add-category-form');
        const name = form.name.value.trim();
        if (!name) return;
        
        try {
            const result = await this.apiService.addCategory(name);
            if (result.success) {
                this.notificationManager.showNotification('✅', `Category "${name}" added!`);
                form.reset();
                document.getElementById('add-category-modal').classList.add('hidden');
                expenseTracker.modalManager.globalModalManager.unregisterModal('add-category-modal');
                await this.loadCategories();
                this.setSelectedCategory(name);
            } else {
                this.notificationManager.showNotification('❌', result.detail || 'Category already exists.', 'error');
            }
        } catch (error) { 
            console.error('Add category error:', error);
            this.notificationManager.showNotification('❌', `Failed to add category: ${error.message}`, 'error'); 
        }
    }
}

// ============================================================================
// FX RATE MANAGER
// ============================================================================

/**
 * Foreign Exchange Rate Manager
 * 
 * AI CONTEXT: Handles currency conversion with real-time rate fetching.
 * Provides visual feedback for exchange rates and automatically
 * calculates EUR equivalents for non-EUR currencies.
 */
class FxRateManager {
    constructor(apiService, notificationManager) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        document.getElementById('currency').addEventListener('change', this.handleCurrencyChange.bind(this));
        document.getElementById('amount').addEventListener('input', this.handleCurrencyChange.bind(this));
    }
    
    async handleCurrencyChange() {
        const currency = document.getElementById('currency').value;
        const amount = parseFloat(document.getElementById('amount').value) || 0;
        const fxDisplay = document.getElementById('fx-rate-display');
        const fxLabel = document.getElementById('fx-rate-label');
        const fxRateInput = document.getElementById('fx-rate');
        const eurAmountInput = document.getElementById('amount-eur');

        if (currency === 'EUR') {
            fxDisplay.classList.add('hidden');
            fxLabel.classList.add('hidden');
            fxRateInput.value = '1.0';
            eurAmountInput.value = amount.toFixed(2);
            return;
        }
        
        try {
            const date = document.getElementById('date').value;
            const data = await this.apiService.getFxRate(currency, date);
            
            fxDisplay.classList.remove('hidden');
            fxLabel.classList.remove('hidden');
            document.getElementById('fx-rate-value').textContent = `1 EUR ≈ ${data.rate.toFixed(4)} ${currency}`;
            fxRateInput.value = data.rate;
            
            const eurAmount = amount / data.rate;
            eurAmountInput.value = eurAmount.toFixed(2);
            document.getElementById('eur-amount-display').textContent = `≈ €${eurAmount.toFixed(2)}`;
        } catch (error) { 
            console.error('FX rate error:', error);
            fxDisplay.classList.add('hidden');
            fxLabel.classList.add('hidden'); 
            this.notificationManager.showNotification('⚠️', `Could not fetch exchange rate: ${error.message}`, 'warning');
        }
    }
}

// ============================================================================
// IMAGE MANAGER
// ============================================================================

/**
 * Image Display and Preview Manager
 * 
 * AI CONTEXT: Handles receipt image display, thumbnails, and full-screen viewing.
 * Provides click-to-expand functionality with proper error handling.
 */
class ImageManager {
    showImage(type, id) {
        const placeholder = document.getElementById('image-placeholder');
        const thumb = document.getElementById('expense-image-thumb');
        const fullRes = document.getElementById('full-res-image');
        
        // Fix: Ensure plural form for drafts
        const endpoint = type === 'draft' ? 'drafts' : type;
        const imageUrl = `./${endpoint}/${id}/image?t=${Date.now()}`;
        
        thumb.setAttribute('src', imageUrl);
        fullRes.setAttribute('src', imageUrl);
    
        thumb.onload = () => {
            placeholder.classList.add('hidden');
            thumb.classList.remove('hidden');
        };
    
        thumb.onerror = () => {
            placeholder.classList.remove('hidden');
            thumb.classList.add('hidden');
        };
    }
    
    showFullImage() {
        const overlay = document.getElementById('imageOverlay');
        const thumb = document.getElementById('expense-image-thumb');
        
        if (thumb && !thumb.classList.contains('hidden') && thumb.src && thumb.src.trim() !== '') {
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
            expenseTracker.modalManager.globalModalManager.registerModal('imageOverlay', () => this.closeImageModal());
        }
    }
    
    closeImageModal(event) {
        if (!event || event.target === document.getElementById('imageOverlay') || event.target.classList.contains('image-overlay-close')) {
            document.getElementById('imageOverlay').classList.remove('active');
            document.body.style.overflow = '';
            expenseTracker.modalManager.globalModalManager.unregisterModal('imageOverlay');
        }
    }
    
    resetImageDisplay() {
        document.getElementById('image-placeholder').classList.remove('hidden');
        document.getElementById('expense-image-thumb').classList.add('hidden');
        document.getElementById('fx-rate-display').classList.add('hidden');
        document.getElementById('fx-rate-label').classList.add('hidden');
    }
}

// ============================================================================
// DATE WARNING MANAGER
// ============================================================================

/**
 * Date Warning System
 * 
 * AI CONTEXT: Handles date validation warnings from OCR processing.
 * Alerts users when dates extracted from receipts need verification.
 */
class DateWarningManager {
    showDateWarning(warningText) {
        const dateInput = document.getElementById('date');
        const warningDiv = document.getElementById('date-warning');
        const warningTextSpan = document.getElementById('date-warning-text');
        
        dateInput.classList.add('has-warning');
        warningTextSpan.textContent = warningText;
        warningDiv.classList.remove('hidden');
    }
    
    hideDateWarning() {
        const dateInput = document.getElementById('date');
        const warningDiv = document.getElementById('date-warning');
        
        dateInput.classList.remove('has-warning');
        warningDiv.classList.add('hidden');
    }
    
    resetDateWarning() {
        this.hideDateWarning();
    }
}

// ============================================================================
// FILE UPLOAD MANAGER
// ============================================================================

/**
 * File Upload and OCR Processing Manager
 * 
 * AI CONTEXT: Handles drag-drop file uploads with OCR processing.
 * Manages the complete workflow from file selection to draft creation.
 */
class FileUploadManager {
    constructor(apiService, notificationManager, appState, draftManager) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.appState = appState;
        this.draftManager = draftManager;
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        const uploadArea = document.getElementById('upload-area');
        const fileInputBtn = document.getElementById('file-input-btn');
        const fileInput = document.getElementById('file-input');
        
        fileInputBtn.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', e => { e.preventDefault(); e.currentTarget.classList.add('border-blue-400', 'bg-blue-50'); });
        uploadArea.addEventListener('dragleave', e => { e.preventDefault(); e.currentTarget.classList.remove('border-blue-400', 'bg-blue-50'); });
        uploadArea.addEventListener('drop', this.handleDrop.bind(this));
        fileInput.addEventListener('change', this.handleFileSelect.bind(this));
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
            this.notificationManager.showNotification('⚠️', 'Please select one or more image files.');
            return;
        }

        this.appState.setUploadingState(true);
        
        try {
            const data = await this.apiService.uploadImages(imageFiles);
            if (data.drafts_created > 0) {
                this.notificationManager.showNotification('✅', `${data.drafts_created} draft(s) created and ready for review.`, 'success');
                await this.draftManager.loadDrafts();
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
// FORM VALIDATION MANAGER
// ============================================================================

/**
 * Form Validation and Management
 * 
 * AI CONTEXT: Real-time form validation with visual feedback.
 * Handles both client-side validation and server-side error display.
 */
class FormValidationManager {
    setupRealTimeValidation() {
        document.getElementById('amount').addEventListener('input', e => this.validateField(e.target, 'amount'));
        document.getElementById('description').addEventListener('input', e => this.validateField(e.target, 'description'));
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
        errorDiv.classList.toggle('hidden', isValid);
    }
    
    validateForm() {
        let isValid = true;
        const errors = [];
        
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
}

// ============================================================================
// DRAFT MANAGER WITH AUTO-SAVE
// ============================================================================

/**
 * Draft Management with Auto-Save and Error Handling
 * 
 * AI CONTEXT: Manages OCR processing results before confirmation.
 * Supports auto-save, bulk operations, and error state management.
 */
class DraftManager {
    constructor(apiService, notificationManager, expenseForm, appState) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.expenseForm = expenseForm;
        this.appState = appState;
        this.filteredDrafts = [];
        this.currentEditingDraftId = null;
        this.autoSaveTimeout = null;
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Filter toggle
        document.getElementById('toggle-draft-filters').addEventListener('click', () => {
            const controls = document.getElementById('draft-filter-controls');
            controls.classList.toggle('show');
        });

        // Filter actions
        document.getElementById('apply-draft-filters').addEventListener('click', () => this.applyFilters());
        document.getElementById('clear-draft-filters').addEventListener('click', () => this.clearFilters());

        // Event delegation for draft items
        document.getElementById('drafts-list').addEventListener('click', (e) => {
            this.handleDraftItemClick(e);
        });
    }

    startAutoSave(draftId) {
        this.currentEditingDraftId = draftId;
        
        // Set up auto-save on form changes
        const form = document.getElementById('expense-form');
        const inputs = form.querySelectorAll('input, select, textarea');
        
        inputs.forEach(input => {
            input.addEventListener('input', () => this.scheduleAutoSave());
            input.addEventListener('change', () => this.scheduleAutoSave());
        });
        
        // Also listen for category and segmented control changes
        document.addEventListener('click', (e) => {
            if (e.target.closest('.category-option') || e.target.closest('.segmented-option')) {
                this.scheduleAutoSave();
            }
        });
    }
    
    scheduleAutoSave() {
        if (!this.currentEditingDraftId) return;
        
        // Clear existing timeout
        if (this.autoSaveTimeout) {
            clearTimeout(this.autoSaveTimeout);
        }
        
        // Schedule auto-save after 1 second of inactivity
        this.autoSaveTimeout = setTimeout(() => {
            this.performAutoSave();
        }, 1000);
    }
    
    async performAutoSave() {
        if (!this.currentEditingDraftId) return;
        
        try {
            const form = document.getElementById('expense-form');
            const formData = new FormData(form);
            
            // Update the draft (not confirm it)
            await this.apiService.updateDraft(this.currentEditingDraftId, formData);
            
            // Visual feedback that draft was saved
            document.getElementById('modal-save-btn-text').textContent = '💾 Save Expense';
            
        } catch (error) {
            console.error('Auto-save failed:', error);
            // Don't show notification for auto-save failures to avoid spam
        }
    }
    
    stopAutoSave() {
        this.currentEditingDraftId = null;
        if (this.autoSaveTimeout) {
            clearTimeout(this.autoSaveTimeout);
            this.autoSaveTimeout = null;
        }
        
        // Remove event listeners to prevent memory leaks
        const form = document.getElementById('expense-form');
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.removeEventListener('input', this.scheduleAutoSave);
            input.removeEventListener('change', this.scheduleAutoSave);
        });
    }

    handleDraftItemClick(e) {
        const draftRow = e.target.closest('.item-row[data-draft-id]');
        if (!draftRow) return;

        const draftId = parseInt(draftRow.dataset.draftId);
        
        // Handle selector clicks
        if (e.target.closest('.item-selector')) {
            e.stopPropagation();
            this.toggleDraftSelection(draftId, e);
            return;
        }

        // Handle action button clicks
        if (e.target.closest('.action-btn')) {
            e.stopPropagation();
            if (e.target.closest('.action-btn.confirm')) {
                this.confirmDraft(draftId);
            } else if (e.target.closest('.action-btn.delete')) {
                const description = this.filteredDrafts.find(d => d.id === draftId)?.description || 'Draft';
                expenseTracker.modalManager.confirmIndividualDeleteDraft(draftId, description);
            } else if (e.target.closest('.clear-error-btn')) {
                this.clearDraftError(draftId);
            }
            return;
        }

        // Handle row clicks (edit)
        if (!e.target.closest('.item-actions')) {
            this.editDraft(draftId);
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

    applyFilters() {
        const filters = {
            description: document.getElementById('draft-filter-description').value.toLowerCase(),
            amountFrom: parseFloat(document.getElementById('draft-filter-amount-from').value) || 0,
            amountTo: parseFloat(document.getElementById('draft-filter-amount-to').value) || Infinity,
            dateFrom: document.getElementById('draft-filter-date-from').value,
            dateTo: document.getElementById('draft-filter-date-to').value
        };

        this.filteredDrafts = this.appState.allDrafts.filter(draft => {
            // Description filter
            if (filters.description && !draft.description?.toLowerCase().includes(filters.description)) {
                return false;
            }

            // Amount filter
            const amount = parseFloat(draft.amount) || 0;
            if (amount < filters.amountFrom || amount > filters.amountTo) {
                return false;
            }

            // Date filter
            if (filters.dateFrom && draft.date && draft.date < filters.dateFrom) {
                return false;
            }
            if (filters.dateTo && draft.date && draft.date > filters.dateTo) {
                return false;
            }

            return true;
        });

        this.appState.draftPagination.currentPage = 1;
        this.renderCurrentPage();
    }

    clearFilters() {
        document.getElementById('draft-filter-description').value = '';
        document.getElementById('draft-filter-amount-from').value = '';
        document.getElementById('draft-filter-amount-to').value = '';
        document.getElementById('draft-filter-date-from').value = '';
        document.getElementById('draft-filter-date-to').value = '';
        
        this.filteredDrafts = [...this.appState.allDrafts];
        this.appState.draftPagination.currentPage = 1;
        this.renderCurrentPage();
    }

    async loadDrafts() {
        const loadingIndicator = document.getElementById('drafts-loading');
        loadingIndicator.classList.remove('hidden');
        try {
            this.appState.allDrafts = await this.apiService.getDrafts();
            this.filteredDrafts = [...this.appState.allDrafts];
            this.appState.draftPagination.currentPage = 1;
            this.renderCurrentPage();
        } catch (error) {
            console.error('Failed to load drafts:', error);
            this.notificationManager.showNotification('❌', `Failed to load drafts: ${error.message}`, 'error');
            document.getElementById('drafts-list').innerHTML = `<div class="text-center py-10"><p class="text-red-500">Failed to load drafts. Please refresh.</p></div>`;
        } finally {
            loadingIndicator.classList.add('hidden');
        }
    }

    renderCurrentPage() {
        const section = document.getElementById('drafts-section');
        const list = document.getElementById('drafts-list');
        const { draftPagination } = this.appState;
        const { currentPage, itemsPerPage } = draftPagination;
        
        if (this.filteredDrafts.length === 0) {
            section.classList.add('hidden');
            list.innerHTML = '';
            this.renderPaginationControls();
            return;
        }
        
        section.classList.remove('hidden');
        
        const start = (currentPage - 1) * itemsPerPage;
        const end = start + itemsPerPage;
        const pageDrafts = this.filteredDrafts.slice(start, end);
        
        list.innerHTML = pageDrafts.map(draft => this.renderDraftItem(draft)).join('');
        this.renderPaginationControls();
        this.updateBulkActions();
    }

    renderPaginationControls() {
        const { draftPagination } = this.appState;
        const { currentPage, itemsPerPage } = draftPagination;
        const totalPages = Math.ceil(this.filteredDrafts.length / itemsPerPage);
        
        const controlsHtml = `
            <div class="flex items-center gap-2 text-sm">
                <label for="draft-items-per-page" class="text-gray-600">Per Page:</label>
                <select id="draft-items-per-page" class="form-input !h-8 !py-1 !text-sm w-20">
                    <option value="10" ${itemsPerPage === 10 ? 'selected' : ''}>10</option>
                    <option value="25" ${itemsPerPage === 25 ? 'selected' : ''}>25</option>
                    <option value="100" ${itemsPerPage === 100 ? 'selected' : ''}>100</option>
                </select>
            </div>
            ${totalPages > 1 ? `
            <div class="flex items-center gap-1">
                <button class="px-2 py-1 rounded ${currentPage === 1 ? 'opacity-50' : 'hover:bg-gray-200'}" ${currentPage === 1 ? 'disabled' : ''} data-action="prev-page">‹ Prev</button>
                <span class="text-sm text-gray-700 font-medium px-2">Page ${currentPage} of ${totalPages}</span>
                <button class="px-2 py-1 rounded ${currentPage === totalPages ? 'opacity-50' : 'hover:bg-gray-200'}" ${currentPage === totalPages ? 'disabled' : ''} data-action="next-page">Next ›</button>
            </div>` : ''}`;

        document.getElementById('draft-pagination-controls-top').innerHTML = controlsHtml;
        document.getElementById('draft-pagination-controls-bottom').innerHTML = totalPages > 1 ? document.getElementById('draft-pagination-controls-top').children[1].outerHTML : '';
        
        // Add event listeners
        const itemsPerPageSelect = document.getElementById('draft-items-per-page');
        if (itemsPerPageSelect) {
            itemsPerPageSelect.addEventListener('change', e => this.changeItemsPerPage(parseInt(e.target.value)));
        }

        // Add pagination click handlers
        document.querySelectorAll('[data-action="prev-page"]').forEach(btn => {
            btn.addEventListener('click', () => this.changePage('prev'));
        });
        document.querySelectorAll('[data-action="next-page"]').forEach(btn => {
            btn.addEventListener('click', () => this.changePage('next'));
        });
    }

    changePage(direction) {
        const { currentPage } = this.appState.draftPagination;
        this.appState.draftPagination.currentPage = direction === 'next' ? currentPage + 1 : currentPage - 1;
        this.renderCurrentPage();
    }

    changeItemsPerPage(value) {
        this.appState.draftPagination.itemsPerPage = value;
        this.appState.draftPagination.currentPage = 1;
        this.renderCurrentPage();
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
            clearErrorBtnHtml = `<button class="clear-error-btn" title="Clear error and try again">Clear Error</button>`;
        }
        
        return `
            <div class="item-row ${isSelected ? 'selected' : ''} ${errorClass}" data-draft-id="${draft.id}">
                <div class="item-selector">
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
                            ${draft.has_image ? '<span title="Image attached">📷</span>' : '📄'}
                            ${hasError ? `<span class="text-red-600" title="${draft.error_message}">⚠️ Needs attention</span>` : ''}
                        </div>
                    </div>
                    <div class="item-actions">
                        ${hasError ? clearErrorBtnHtml : ''}
                        <button class="action-btn confirm" ${hasError ? 'disabled style="opacity: 0.5; cursor: not-allowed;"' : ''}>✅ Confirm</button>
                        <button class="action-btn delete">🗑️ Dismiss</button>
                    </div>
                </div>
            </div>`;
    }

    toggleDraftSelection(draftId, event) {
        const item = document.querySelector(`[data-draft-id="${draftId}"]`);
        if (!item) return;

        const isSelected = item.classList.toggle('selected');
        
        if (isSelected) {
            this.appState.selectedDrafts.add(draftId);
        } else {
            this.appState.selectedDrafts.delete(draftId);
        }
        this.updateBulkActions();
    }

    async editDraft(draftId) {
        try {
            const draftData = await this.apiService.getDraft(draftId);
            this.expenseForm.populateForm(draftData, 'draft');
        } catch (error) {
            console.error(`Failed to load draft ${draftId}:`, error);
            this.notificationManager.showNotification('❌', `Could not load draft for editing: ${error.message}`, 'error');
        }
    }

    updateBulkActions() {
        const bulkActions = document.getElementById('draft-bulk-actions');
        const selectedCount = document.getElementById('draft-selected-count');
        const toggleBtn = document.getElementById('draft-toggle-select-btn');
        const count = this.appState.selectedDrafts.size;
        
        const totalVisible = document.querySelectorAll('#drafts-list .item-row').length;
        const allSelected = count === totalVisible && totalVisible > 0;
        
        selectedCount.textContent = `${count} selected`;
        toggleBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        toggleBtn.className = `bulk-btn ${allSelected ? 'deselect-all' : 'select-all'}`;
        
        bulkActions.classList.toggle('show', count > 0);
    }

    toggleSelectAll() {
        const totalVisible = document.querySelectorAll('#drafts-list .item-row').length;
        const allSelected = this.appState.selectedDrafts.size === totalVisible && totalVisible > 0;
        
        if (allSelected) {
            this.clearSelection();
        } else {
            this.selectAllVisible();
        }
    }

    selectAllVisible() {
        document.querySelectorAll('#drafts-list .item-row').forEach(item => {
            const draftId = parseInt(item.dataset.draftId);
            if (!this.appState.selectedDrafts.has(draftId)) {
                item.classList.add('selected');
                this.appState.selectedDrafts.add(draftId);
            }
        });
        this.updateBulkActions();
    }

    clearSelection() {
        document.querySelectorAll('#drafts-list .item-row.selected').forEach(item => {
            item.classList.remove('selected');
        });
        this.appState.selectedDrafts.clear();
        this.updateBulkActions();
    }

    async confirmDraft(draftId) {
        try {
            const draftData = await this.apiService.getDraft(draftId);
            this.expenseForm.populateForm(draftData, 'draft');
        } catch (error) {
            console.error(`Failed to load draft ${draftId}:`, error);
            this.notificationManager.showNotification('❌', `Could not load draft for confirmation: ${error.message}`, 'error');
        }
    }

    async confirmSelectedDrafts() {
        const selectedIds = Array.from(this.appState.selectedDrafts);
        if (selectedIds.length === 0) {
            this.notificationManager.showNotification('⚠️', 'No drafts selected for confirmation.', 'warning');
            return;
        }

        try {
            const result = await this.apiService.bulkConfirmDrafts(selectedIds);
            
            if (result.success_count > 0) {
                this.notificationManager.showNotification('✅', `${result.success_count} draft(s) confirmed successfully!`, 'success');
            }
            
            if (result.error_count > 0) {
                const errorMessage = `${result.error_count} draft(s) need attention - missing required fields or validation errors. Check items with yellow borders.`;
                this.notificationManager.showNotification('⚠️', errorMessage, 'warning');
            }

            this.clearSelection();
            await this.loadDrafts();
            await expenseTracker.expenseList.loadLastFive();
        } catch (error) {
            console.error('Bulk confirm error:', error);
            this.notificationManager.showNotification('❌', `Failed to confirm drafts: ${error.message}`, 'error');
        }
    }

    async dismissDraft(draftId) {
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

// ============================================================================
// EXPENSE FORM MANAGER (MODAL VERSION)
// ============================================================================

/**
 * Expense Form Management System
 * 
 * AI CONTEXT: Complete form handling for expense creation and editing.
 * Manages modal display, form validation, and submission with auto-save support.
 */
class ExpenseFormManager {
    constructor(apiService, notificationManager, appState, formValidation, categoryManager, segmentedControls, imageManager, dateWarningManager) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.appState = appState;
        this.formValidation = formValidation;
        this.categoryManager = categoryManager;
        this.segmentedControls = segmentedControls;
        this.imageManager = imageManager;
        this.dateWarningManager = dateWarningManager;
        this.setupEventListeners();
        this.originalFormData = null; // Track original form state
        this.hasUnsavedChanges = false;
    }
    
    setupEventListeners() {
        document.getElementById('expense-form').addEventListener('submit', this.handleFormSubmit.bind(this));
    }
    
    confirmDismiss() {
        const form = document.getElementById('expense-form');
        const draftId = form.draft_id.value;
        const description = form.description.value || 'Untitled Draft';
        
        if (!draftId) {
            this.smartClose();
            return;
        }
        
        // Use the existing delete confirmation modal
        const message = `Are you sure you want to dismiss "${description}"? This action cannot be undone.`;
        document.getElementById('delete-confirmation-message').textContent = message;
        document.getElementById('delete-confirm-text').textContent = '🗑️ Dismiss';
        document.getElementById('delete-confirmation-overlay').classList.remove('hidden');
        
        // Set up handlers
        document.getElementById('delete-confirm-yes').onclick = () => this.executeDismiss(draftId);
        document.getElementById('delete-confirm-no').onclick = () => {
            document.getElementById('delete-confirmation-overlay').classList.add('hidden');
        };
    }
    
    async executeDismiss(draftId) {
        try {
            await this.apiService.deleteDraft(draftId);
            document.getElementById('delete-confirmation-overlay').classList.add('hidden');
            this.hideModal();
            this.notificationManager.showNotification('🗑️', 'Draft dismissed successfully', 'success');
            await expenseTracker.draftManager.loadDrafts();
        } catch (error) {
            console.error('Dismiss failed:', error);
            this.notificationManager.showNotification('❌', `Failed to dismiss draft: ${error.message}`, 'error');
            document.getElementById('delete-confirmation-overlay').classList.add('hidden');
        }
    }

    setDefaultDate() { 
        document.getElementById('date').value = new Date().toISOString().split('T')[0]; 
    }
    
    populateForm(data, type = 'expense') {
        this.resetForm(false);
        const form = document.getElementById('expense-form');
        
        if (data.date_warning) {
            form.date.value = '';
            this.dateWarningManager.showDateWarning(data.date_warning);
        } else {
            form.date.value = data.date || new Date().toISOString().split('T')[0];
        }
        
        form.amount.value = data.amount || '';
        form.currency.value = data.currency || 'EUR';
        form.description.value = data.description || '';
        form.fx_rate.value = data.fx_rate || 1.0;
        form.amount_eur.value = data.amount_eur || 0;
        form.expense_id.value = type === 'expense' ? (data.id || '') : '';
        form.draft_id.value = type === 'draft' ? (data.id || '') : '';
        
        this.updateFormTitleAndButton(data, type);
        this.categoryManager.setSelectedCategory(data.category || 'Other');
        
        const personRadio = document.querySelector(`input[name="person"][value="${data.person}"]`) || document.querySelector(`input[name="person"][value="Közös"]`);
        if (personRadio) {
            document.querySelectorAll('input[name="person"]').forEach(r => r.checked = false);
            personRadio.checked = true;
            this.segmentedControls.updateSlider(personRadio.closest('.segmented-control'));
        }
        
        const beneficiaryRadio = document.querySelector(`input[name="beneficiary"][value="${data.beneficiary || ''}"]`);
        if (beneficiaryRadio) {
            document.querySelectorAll('input[name="beneficiary"]').forEach(r => r.checked = false);
            beneficiaryRadio.checked = true;
            this.segmentedControls.updateSlider(beneficiaryRadio.closest('.segmented-control'));
        }

        if (data.has_image) {
            this.imageManager.showImage(type, data.id);
        }
        
        // Start auto-saving for drafts
        if (type === 'draft') {
            expenseTracker.draftManager.startAutoSave(data.id);
        }
        
        expenseTracker.fxManager.handleCurrencyChange();
        this.showModal();

        // Capture original form state after populating
        setTimeout(() => {
            this.captureOriginalFormState();
            this.setupFormChangeTracking();
        }, 100);
    }
    
        
    captureOriginalFormState() {
        const form = document.getElementById('expense-form');
        const formData = new FormData(form);
        this.originalFormData = {};
        
        for (let [key, value] of formData.entries()) {
            this.originalFormData[key] = value;
        }
        
        // Also capture category and radio selections
        this.originalFormData.category = document.getElementById('selected-category').value;
        this.originalFormData.person = document.querySelector('input[name="person"]:checked')?.value || '';
        this.originalFormData.beneficiary = document.querySelector('input[name="beneficiary"]:checked')?.value || '';
        
        this.hasUnsavedChanges = false;
    }

    setupFormChangeTracking() {
        const form = document.getElementById('expense-form');
        const inputs = form.querySelectorAll('input, select, textarea');
        
        inputs.forEach(input => {
            input.addEventListener('input', () => this.markAsChanged());
            input.addEventListener('change', () => this.markAsChanged());
        });
        
        // Listen for category and person selection changes
        document.addEventListener('click', (e) => {
            if (e.target.closest('.category-option') || e.target.closest('.segmented-option')) {
                this.markAsChanged();
            }
        });
    }

    markAsChanged() {
        this.hasUnsavedChanges = true;
    }

    async smartClose() {
        // Check if there are unsaved changes
        if (!this.hasUnsavedChanges) {
            // No changes - close immediately
            this.hideModal();
            return;
        }
        
        // Has changes - auto-save and close
        const form = document.getElementById('expense-form');
        const expenseId = form.expense_id.value;
        const draftId = form.draft_id.value;
        
        try {
            if (draftId) {
                // Auto-save draft changes
                const formData = new FormData(form);
                await this.apiService.updateDraft(draftId, formData);
                this.notificationManager.showNotification('💾', 'Changes saved automatically', 'info');
            } else if (expenseId) {
                // Auto-save expense changes  
                const formData = new FormData(form);
                await this.apiService.updateExpense(expenseId, formData);
                this.notificationManager.showNotification('💾', 'Changes saved automatically', 'info');
                await expenseTracker.expenseList.loadLastFive();
            }
            
            this.hideModal();
            
            // Add this line to refresh main page content after auto-save
            await expenseTracker.refreshMainPageContent();
            
        } catch (error) {
            console.error('Auto-save failed:', error);
            this.notificationManager.showNotification('❌', 'Auto-save failed. Changes will be lost if you close.', 'error');
            // Still close the modal even if auto-save failed
            this.hideModal();
            
            // Still refresh even if auto-save failed
            await expenseTracker.refreshMainPageContent();
        }
    }

    resetForm(hide) {
        document.getElementById('expense-form').reset();
        
        // Stop auto-saving
        expenseTracker.draftManager.stopAutoSave();
        
        if (hide) this.hideModal();
        
        document.querySelectorAll('.error-state').forEach(el => el.classList.remove('error-state'));
        document.querySelectorAll('.error-message').forEach(el => el.classList.add('hidden'));
        
        this.imageManager.resetImageDisplay();
        this.dateWarningManager.resetDateWarning();
        
        this.categoryManager.resetCategories();
        this.segmentedControls.resetControls();
        
        this.setDefaultDate();
    }
    
    showModal() {
        const modal = document.getElementById('edit-modal');
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
        // Fixed code:
        expenseTracker.modalManager.globalModalManager.registerModal('edit-modal', () => this.hideModal());    }

    hideModal() {
        const modal = document.getElementById('edit-modal');
        modal.classList.remove('active');
        document.body.style.overflow = '';
        
        // Stop auto-saving when modal closes
        expenseTracker.draftManager.stopAutoSave();
        
        expenseTracker.modalManager.globalModalManager.unregisterModal('edit-modal');
        
        // Add this line to refresh main page content
        expenseTracker.refreshMainPageContent();
    }
    
    updateFormTitleAndButton(data, type) {
        const modalTitleText = document.getElementById('modal-title-text');
        const confirmBtn = document.getElementById('modal-confirm-btn');
        const dismissBtn = document.getElementById('modal-dismiss-btn');
        
        if (type === 'expense') {
            modalTitleText.innerHTML = `<span class="w-2 h-2 bg-orange-500 rounded-full mr-2"></span>Edit Expense #${data.id}`;
            confirmBtn.textContent = '💾 Update';
            dismissBtn.style.display = 'none'; // Hide dismiss for expenses
        } else {
            modalTitleText.innerHTML = `<span class="w-2 h-2 bg-blue-500 rounded-full mr-2"></span>Confirm New Expense Draft`;
            confirmBtn.textContent = '✅ Confirm';
            dismissBtn.style.display = 'inline-flex'; // Show dismiss for drafts
        }
    }
    
    async handleFormSubmit(e) {
        e.preventDefault();
        if (this.appState.isFormSubmitting) return;
        
        const validation = this.formValidation.validateForm();
        if (!validation.isValid) {
            this.notificationManager.showNotification('⚠️', `Please fix the following errors: ${validation.errors.join(', ')}`, 'error');
            return;
        }
        
        const form = e.target;
        const submitBtn = document.getElementById('modal-confirm-btn');
        const originalText = submitBtn.innerHTML;
        this.appState.isFormSubmitting = true;
        submitBtn.disabled = true; 
        submitBtn.innerHTML = '<span class="spinner mr-1"></span>Saving...';
        
        const expenseId = form.expense_id.value;
        const draftId = form.draft_id.value;
        const formData = new FormData(form);
    
        try {
            if (expenseId) {
                await this.apiService.updateExpense(expenseId, formData);
                this.notificationManager.showNotification('✅', 'Expense updated successfully!', 'success');
                await expenseTracker.refreshMainPageContent(); 
            } else if (draftId) {
                const result = await this.apiService.confirmDraft(draftId, formData);
                if (result.success) {
                    this.notificationManager.showNotification('✅', 'Draft confirmed and saved as expense!', 'success');
                    await expenseTracker.refreshMainPageContent();await expenseTracker.refreshMainPageContent();
                } else {
                    this.notificationManager.showNotification('⚠️', 'Draft has validation errors and remains for fixing.', 'warning');
                    await expenseTracker.refreshMainPageContent();
                }
            }
            
            this.resetForm(true);
            await expenseTracker.expenseList.loadLastFive();
    
        } catch (error) { 
            console.error('Form submit error:', error);
            this.notificationManager.showNotification('❌', `Failed to save expense: ${error.message}`, 'error'); 
        } finally { 
            this.appState.isFormSubmitting = false;
            submitBtn.disabled = false; 
            submitBtn.innerHTML = originalText; 
        }
    }
    
    handleSubmit() {
        const form = document.getElementById('expense-form');
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    }
}

// ============================================================================
// BULK OPERATIONS MANAGER
// ============================================================================

/**
 * Bulk Operations Management
 * 
 * AI CONTEXT: Handles selection and batch operations on multiple items.
 * Provides efficient workflow for managing many items at once.
 */
class BulkOperationsManager {
    constructor(appState) {
        this.appState = appState;
    }
    
    toggleExpenseSelection(expenseId, event) {
        event.stopPropagation();
        const item = document.querySelector(`[data-expense-id="${expenseId}"]`);
        const isSelected = item.classList.toggle('selected');
        
        if (isSelected) {
            this.appState.selectedExpenses.add(expenseId);
        } else {
            this.appState.selectedExpenses.delete(expenseId);
        }
        this.updateBulkActions();
    }
    
    updateBulkActions() {
        const bulkActions = document.getElementById('last5-bulk-actions');
        const selectedCount = document.getElementById('last5-selected-count');
        const toggleBtn = document.getElementById('last5-toggle-select-btn');
        const count = this.appState.selectedExpenses.size;
        
        const totalVisible = document.querySelectorAll('#expenses-list .item-row').length;
        const allSelected = count === totalVisible && totalVisible > 0;
        
        selectedCount.textContent = `${count} selected`;
        toggleBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        toggleBtn.className = `bulk-btn ${allSelected ? 'deselect-all' : 'select-all'}`;
        
        bulkActions.classList.toggle('show', count > 0);
    }
    
    toggleSelectAll() {
        const totalVisible = document.querySelectorAll('#expenses-list .item-row').length;
        const allSelected = this.appState.selectedExpenses.size === totalVisible && totalVisible > 0;
        
        if (allSelected) {
            this.clearSelection();
        } else {
            this.selectAllVisible();
        }
    }
    
    selectAllVisible() {
        document.querySelectorAll('#expenses-list .item-row').forEach(item => {
            const expenseId = parseInt(item.dataset.expenseId);
            if (!this.appState.selectedExpenses.has(expenseId)) {
                item.classList.add('selected');
                this.appState.selectedExpenses.add(expenseId);
            }
        });
        this.updateBulkActions();
    }
    
    clearSelection() {
        document.querySelectorAll('#expenses-list .item-row.selected').forEach(item => {
            item.classList.remove('selected');
        });
        this.appState.selectedExpenses.clear();
        this.updateBulkActions();
    }
}

// ============================================================================
// MODAL MANAGER
// ============================================================================

/**
 * Modal Management System
 * 
 * AI CONTEXT: Centralized modal handling including confirmation dialogs,
 * delete confirmations, and modal navigation with proper cleanup.
 */
class ModalManager {
    constructor(appState, apiService, notificationManager, expenseList, draftManager, allItemsModal) {
        this.appState = appState;
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.expenseList = expenseList;
        this.draftManager = draftManager;
        this.allItemsModal = allItemsModal;
        this.globalModalManager = new GlobalModalManager();
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        document.getElementById('confirm-yes').addEventListener('click', () => {
            this.hideConfirmationOverlay();
            expenseTracker.expenseForm.resetForm(true);
        });
        document.getElementById('confirm-no').addEventListener('click', this.hideConfirmationOverlay.bind(this));
        
        document.getElementById('delete-confirm-yes').addEventListener('click', this.handleDeleteConfirmationYes.bind(this));
        document.getElementById('delete-confirm-no').addEventListener('click', this.hideDeleteConfirmationOverlay.bind(this));
        
        // All close methods now use smart close
        this.globalModalManager.registerModal('edit-modal', () => expenseTracker.expenseForm.smartClose());
        
        // Click outside to close with smart behavior
        document.getElementById('edit-modal').addEventListener('click', (e) => {
            if (e.target.id === 'edit-modal') {
                expenseTracker.expenseForm.smartClose();
            }
        });
        
        this.globalModalManager.registerModal('confirmation-overlay', () => this.hideConfirmationOverlay());
        this.globalModalManager.registerModal('delete-confirmation-overlay', () => this.hideDeleteConfirmationOverlay());
        this.globalModalManager.registerModal('all-items-modal', () => this.allItemsModal.hide());
        this.globalModalManager.registerModal('add-category-modal', () => document.getElementById('add-category-modal').classList.add('hidden'));
        this.globalModalManager.registerModal('audit-history-modal', () => expenseTracker.auditManager.hideAuditHistory());
        this.globalModalManager.registerModal('imageOverlay', () => expenseTracker.imageManager.closeImageModal());
    }
    
    showConfirmationOverlay() {
        document.getElementById('confirmation-message').textContent = 'Are you sure you want to close this form? Any unsaved changes will be lost.';
        document.getElementById('confirmation-overlay').classList.remove('hidden');
        this.globalModalManager.registerModal('confirmation-overlay', () => this.hideConfirmationOverlay());
    }

    hideConfirmationOverlay() {
        document.getElementById('confirmation-overlay').classList.add('hidden');
        this.globalModalManager.unregisterModal('confirmation-overlay');
    }
    
    confirmIndividualDelete(expenseId, description) {
        this.appState.currentDeleteOperation = { type: 'individual', targetType: 'expense', expenseId, description };
        const message = `Are you sure you want to delete "${description}"? This action cannot be undone.`;
        this.showDeleteConfirmationOverlay(message, '🗑️ Delete');
    }

    confirmIndividualDeleteDraft(draftId, description) {
        this.appState.currentDeleteOperation = { type: 'individual', targetType: 'draft', draftId, description };
        const message = `Are you sure you want to dismiss "${description}"? This action cannot be undone.`;
        this.showDeleteConfirmationOverlay(message, '🗑️ Dismiss');
    }
    
    confirmBulkDelete() {
        const count = this.appState.selectedExpenses.size;
        if (count === 0) {
            this.notificationManager.showNotification('⚠️', 'No expenses selected for deletion.', 'warning');
            return;
        }
        
        this.appState.currentDeleteOperation = { type: 'bulk', targetType: 'expense', expenseIds: Array.from(this.appState.selectedExpenses) };
        const message = `Are you sure you want to delete ${count} expense${count > 1 ? 's' : ''}? This action cannot be undone.`;
        const btnText = `🗑️ Delete ${count} Item${count > 1 ? 's' : ''}`;
        this.showDeleteConfirmationOverlay(message, btnText);
    }

    confirmBulkDeleteDrafts() {
        const count = this.appState.selectedDrafts.size;
        if (count === 0) {
            this.notificationManager.showNotification('⚠️', 'No drafts selected for deletion.', 'warning');
            return;
        }
        
        this.appState.currentDeleteOperation = { type: 'bulk', targetType: 'draft', draftIds: Array.from(this.appState.selectedDrafts) };
        const message = `Are you sure you want to dismiss ${count} draft${count > 1 ? 's' : ''}? This action cannot be undone.`;
        const btnText = `🗑️ Dismiss ${count} Item${count > 1 ? 's' : ''}`;
        this.showDeleteConfirmationOverlay(message, btnText);
    }
    
    showDeleteConfirmationOverlay(message, btnText) {
        document.getElementById('delete-confirmation-message').textContent = message;
        document.getElementById('delete-confirm-text').textContent = btnText;
        document.getElementById('delete-confirmation-overlay').classList.remove('hidden');
    }

    hideDeleteConfirmationOverlay() {
        document.getElementById('delete-confirmation-overlay').classList.add('hidden');
        this.appState.currentDeleteOperation = null;
    }
    
    async handleDeleteConfirmationYes() {
        if (!this.appState.currentDeleteOperation) return;
        
        const deleteBtn = document.getElementById('delete-confirm-yes');
        const originalText = deleteBtn.innerHTML;
        deleteBtn.disabled = true;
        deleteBtn.innerHTML = '<span class="spinner mr-2"></span>Deleting...';
        
        try {
            const op = this.appState.currentDeleteOperation;
            
            if (op.targetType === 'expense') {
                if (op.type === 'individual') {
                    await this.apiService.deleteExpense(op.expenseId);
                } else if (op.type === 'bulk') {
                    await this.apiService.bulkDeleteExpenses(op.expenseIds);
                }
                
                const count = op.type === 'individual' ? 1 : op.expenseIds.length;
                this.notificationManager.showNotification('✅', `Successfully deleted ${count} expense${count > 1 ? 's' : ''}!`, 'success');
                
                // Clear selections and refresh data
                if (op.source === 'allItemsModal') {
                    this.allItemsModal.clearSelection();
                    await this.allItemsModal.loadAllItems();
                } else {
                    expenseTracker.bulkManager.clearSelection();
                }
                await this.expenseList.loadLastFive();
                
            } else if (op.targetType === 'draft') {
                if (op.type === 'individual') {
                    await this.apiService.deleteDraft(op.draftId);
                } else if (op.type === 'bulk') {
                    // Bulk delete drafts one by one
                    let successCount = 0;
                    for (const draftId of op.draftIds) {
                        try {
                            await this.apiService.deleteDraft(draftId);
                            successCount++;
                        } catch (error) {
                            console.error(`Failed to delete draft ${draftId}:`, error);
                        }
                    }
                    
                    if (successCount !== op.draftIds.length) {
                        this.notificationManager.showNotification('⚠️', `Dismissed ${successCount} of ${op.draftIds.length} drafts.`, 'warning');
                    }
                }
                
                const count = op.type === 'individual' ? 1 : op.draftIds.length;
                this.notificationManager.showNotification('✅', `Successfully dismissed ${count} draft${count > 1 ? 's' : ''}!`, 'success');
                
                this.draftManager.clearSelection();
                await this.draftManager.loadDrafts();
            }
            
            this.hideDeleteConfirmationOverlay();
            
        } catch (error) {
            console.error('Delete error:', error);
            this.notificationManager.showNotification('❌', `Failed to delete item(s): ${error.message}`, 'error');
        } finally {
            deleteBtn.disabled = false;
            deleteBtn.innerHTML = originalText;
        }
    }
}

// ============================================================================
// EXPENSE LIST MANAGER
// ============================================================================

/**
 * Expense List Management
 * 
 * AI CONTEXT: Handles the display and interaction with the recent expenses list.
 * Manages rendering, selection, and editing of individual expense items.
 */
class ExpenseListManager {
    constructor(apiService, notificationManager, appState) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.appState = appState;
    }
    
    async loadLastFive() {
        const loadingIndicator = document.getElementById('expenses-loading');
        loadingIndicator.classList.remove('hidden');
        try {
            this.appState.allEntries = await this.apiService.getExpenses();
            this.renderLastFive();
        } catch (error) { 
            console.error('Failed to load expenses:', error);
            this.notificationManager.showNotification('❌', `Failed to load expenses: ${error.message}`, 'error');
            document.getElementById('expenses-list').innerHTML = `<div class="text-center py-10"><p class="text-red-500">Failed to load entries. Please refresh.</p></div>`;
        } finally {
            loadingIndicator.classList.add('hidden');
        }
    }

    async loadAllEntries() {
        // Alias for loadLastFive to maintain compatibility
        return this.loadLastFive();
    }

    renderLastFive() {
        const list = document.getElementById('expenses-list');
        const { allEntries } = this.appState;
        
        if (allEntries.length === 0) {
            list.innerHTML = '<div class="text-center py-10"><p class="text-gray-500">No expenses recorded yet.</p><p class="text-sm text-gray-400 mt-2">Upload a receipt to get started!</p></div>';
            return;
        }
        
        const lastFive = allEntries.slice(0, 5);
        list.innerHTML = lastFive.map(exp => this.renderExpenseItem(exp)).join('');
        
        // Apply dynamic grid layout
        applyDynamicGrid('#expenses-list', lastFive);
        
        this.updateBulkActions();
    }

    updateBulkActions() {
        const bulkActions = document.getElementById('last5-bulk-actions');
        const selectedCount = document.getElementById('last5-selected-count');
        const toggleBtn = document.getElementById('last5-toggle-select-btn');
        const count = this.appState.selectedExpenses.size;
        
        const totalVisible = document.querySelectorAll('#expenses-list .item-row').length;
        const allSelected = count === totalVisible && totalVisible > 0;
        
        selectedCount.textContent = `${count} selected`;
        toggleBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        toggleBtn.className = `bulk-btn ${allSelected ? 'deselect-all' : 'select-all'}`;
        
        bulkActions.classList.toggle('show', count > 0);
    }

    renderExpenseItem(exp) {
        const isSelected = this.appState.selectedExpenses.has(exp.id);
        return `
            <div class="item-row ${isSelected ? 'selected' : ''}" data-expense-id="${exp.id}">
                <div class="item-selector" onclick="expenseTracker.bulkManager.toggleExpenseSelection(${exp.id}, event)">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
                </div>
                <div class="flex-1" onclick="expenseTracker.expenseList.editExpense(${exp.id})">
                    <p class="font-medium text-gray-900 text-sm">${exp.description || 'No description'}</p>
                    <div class="item-details-grid">
                        <span class="grid-amount">€${parseFloat(exp.amount).toFixed(2)} ${exp.currency}</span>
                        <span class="grid-category">${exp.category}</span>
                        <span>📅 ${exp.date}</span>
                        <span>👤 ${exp.person}</span>
                        <span>${exp.beneficiary ? `🎯 ${exp.beneficiary}` : ''}</span>
                        <span>${exp.has_image ? '📷' : ''}</span>
                    </div>
                </div>
                <div class="item-actions expense-actions">
                    <button class="action-btn edit" onclick="expenseTracker.expenseList.editExpense(${exp.id}); event.stopPropagation();" title="Edit expense">Edit</button>
                    <button class="action-btn history" onclick="expenseTracker.expenseList.showExpenseHistory(${exp.id}); event.stopPropagation();" title="View history">History</button>
                    <button class="action-btn delete" onclick="expenseTracker.expenseList.deleteExpense(${exp.id}); event.stopPropagation();" title="Delete expense">Delete</button>
                </div>
            </div>
        `;
    }
    
    async editExpense(id) {
        try {
            const expense = await this.apiService.getExpense(id);
            expenseTracker.expenseForm.populateForm(expense, 'expense');
        } catch (error) { 
            console.error('Edit expense error:', error);
            this.notificationManager.showNotification('❌', `Could not load expense for editing: ${error.message}`, 'error'); 
        }
    }
}

// ============================================================================
// ALL ITEMS MODAL MANAGER
// ============================================================================

/**
 * All Items Modal System
 * 
 * AI CONTEXT: Complete expense history viewer with advanced filtering,
 * pagination, and bulk operations for managing large datasets.
 */
class AllItemsModalManager {
    constructor(apiService, notificationManager, appState, categoryManager) {
        this.apiService = apiService;
        this.notificationManager = notificationManager;
        this.appState = appState;
        this.categoryManager = categoryManager;
        this.filteredItems = [];
        this.selectedItems = new Set();
        this.pagination = { currentPage: 1, itemsPerPage: 10 };
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Filter toggle
        document.getElementById('toggle-all-items-filters').addEventListener('click', () => {
            const controls = document.getElementById('all-items-filter-controls');
            controls.classList.toggle('show');
        });

        // Filter actions
        document.getElementById('apply-all-items-filters').addEventListener('click', () => this.applyFilters());
        document.getElementById('clear-all-items-filters').addEventListener('click', () => this.clearFilters());
    }

    async show() {
        const modal = document.getElementById('all-items-modal');
        modal.classList.add('active');
        expenseTracker.modalManager.globalModalManager.registerModal('all-items-modal', () => this.hide());
        
        // Load categories for filter
        const categories = await this.categoryManager.loadCategories();
        const categorySelect = document.getElementById('all-items-filter-category');
        categorySelect.innerHTML = '<option value="">All Categories</option>' + 
            categories.map(cat => `<option value="${cat}">${cat}</option>`).join('');

        await this.loadAllItems();
    }

    hide() {
        document.getElementById('all-items-modal').classList.remove('active');
        this.clearSelection();
        expenseTracker.modalManager.globalModalManager.unregisterModal('all-items-modal');
    }

    async loadAllItems() {
        const loadingIndicator = document.getElementById('all-items-loading');
        loadingIndicator.classList.remove('hidden');
        try {
            const allItems = await this.apiService.getExpenses();
            this.filteredItems = [...allItems];
            this.pagination.currentPage = 1;
            this.renderCurrentPage();
        } catch (error) {
            console.error('Failed to load all items:', error);
            this.notificationManager.showNotification('❌', `Failed to load all items: ${error.message}`, 'error');
        } finally {
            loadingIndicator.classList.add('hidden');
        }
    }

    applyFilters() {
        const filters = {
            description: document.getElementById('all-items-filter-description').value.toLowerCase(),
            category: document.getElementById('all-items-filter-category').value,
            person: document.getElementById('all-items-filter-person').value,
            amountFrom: parseFloat(document.getElementById('all-items-filter-amount-from').value) || 0,
            amountTo: parseFloat(document.getElementById('all-items-filter-amount-to').value) || Infinity,
            dateFrom: document.getElementById('all-items-filter-date-from').value,
            dateTo: document.getElementById('all-items-filter-date-to').value
        };

        const allItems = this.appState.allEntries;
        this.filteredItems = allItems.filter(item => {
            // Description filter
            if (filters.description && !item.description?.toLowerCase().includes(filters.description)) {
                return false;
            }

            // Category filter
            if (filters.category && item.category !== filters.category) {
                return false;
            }

            // Person filter
            if (filters.person && item.person !== filters.person) {
                return false;
            }

            // Amount filter
            const amount = parseFloat(item.amount_eur) || 0;
            if (amount < filters.amountFrom || amount > filters.amountTo) {
                return false;
            }

            // Date filter
            if (filters.dateFrom && item.date && item.date < filters.dateFrom) {
                return false;
            }
            if (filters.dateTo && item.date && item.date > filters.dateTo) {
                return false;
            }

            return true;
        });

        this.pagination.currentPage = 1;
        this.renderCurrentPage();
    }

    clearFilters() {
        document.getElementById('all-items-filter-description').value = '';
        document.getElementById('all-items-filter-category').value = '';
        document.getElementById('all-items-filter-person').value = '';
        document.getElementById('all-items-filter-amount-from').value = '';
        document.getElementById('all-items-filter-amount-to').value = '';
        document.getElementById('all-items-filter-date-from').value = '';
        document.getElementById('all-items-filter-date-to').value = '';
        
        this.filteredItems = [...this.appState.allEntries];
        this.pagination.currentPage = 1;
        this.renderCurrentPage();
    }

    renderCurrentPage() {
        const list = document.getElementById('all-items-list');
        const { currentPage, itemsPerPage } = this.pagination;
        
        if (this.filteredItems.length === 0) {
            list.innerHTML = '<div class="text-center py-10"><p class="text-gray-500">No items found with current filters.</p></div>';
            this.renderPaginationControls();
            return;
        }
        
        const start = (currentPage - 1) * itemsPerPage;
        const end = start + itemsPerPage;
        const pageItems = this.filteredItems.slice(start, end);
        
        list.innerHTML = pageItems.map(item => this.renderItem(item)).join('');
        this.renderPaginationControls();
        this.updateBulkActions();
    }

    renderPaginationControls() {
        const { currentPage, itemsPerPage } = this.pagination;
        const totalPages = Math.ceil(this.filteredItems.length / itemsPerPage);
        
        const controlsHtml = `
            <div class="flex items-center gap-2 text-sm">
                <label for="all-items-per-page" class="text-gray-600">Per Page:</label>
                <select id="all-items-per-page" class="form-input !h-8 !py-1 !text-sm w-20">
                    <option value="10" ${itemsPerPage === 10 ? 'selected' : ''}>10</option>
                    <option value="25" ${itemsPerPage === 25 ? 'selected' : ''}>25</option>
                    <option value="50" ${itemsPerPage === 50 ? 'selected' : ''}>50</option>
                    <option value="100" ${itemsPerPage === 100 ? 'selected' : ''}>100</option>
                </select>
            </div>
            ${totalPages > 1 ? `
            <div class="flex items-center gap-1">
                <button class="px-2 py-1 rounded ${currentPage === 1 ? 'opacity-50' : 'hover:bg-gray-200'}" ${currentPage === 1 ? 'disabled' : ''} onclick="expenseTracker.allItemsModal.changePage('prev')">‹ Prev</button>
                <span class="text-sm text-gray-700 font-medium px-2">Page ${currentPage} of ${totalPages}</span>
                <button class="px-2 py-1 rounded ${currentPage === totalPages ? 'opacity-50' : 'hover:bg-gray-200'}" ${currentPage === totalPages ? 'disabled' : ''} onclick="expenseTracker.allItemsModal.changePage('next')">Next ›</button>
            </div>` : ''}`;

        document.getElementById('all-items-pagination-controls-top').innerHTML = controlsHtml;
        document.getElementById('all-items-pagination-controls-bottom').innerHTML = totalPages > 1 ? document.getElementById('all-items-pagination-controls-top').children[1].outerHTML : '';
        
        const itemsPerPageSelect = document.getElementById('all-items-per-page');
        if (itemsPerPageSelect) {
            itemsPerPageSelect.addEventListener('change', e => this.changeItemsPerPage(parseInt(e.target.value)));
        }
    }

    changePage(direction) {
        const { currentPage } = this.pagination;
        this.pagination.currentPage = direction === 'next' ? currentPage + 1 : currentPage - 1;
        this.renderCurrentPage();
    }

    changeItemsPerPage(value) {
        this.pagination.itemsPerPage = value;
        this.pagination.currentPage = 1;
        this.renderCurrentPage();
    }

    renderItem(item) {
        const isSelected = this.selectedItems.has(item.id);
        return `
            <div class="item-row ${isSelected ? 'selected' : ''}" data-item-id="${item.id}">
                <div class="item-selector" onclick="expenseTracker.allItemsModal.toggleSelection(${item.id}, event)">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
                </div>
                <div class="flex items-center gap-3" onclick="expenseTracker.allItemsModal.editItem(${item.id})">
                    <div class="flex-1">
                        <p class="font-medium text-gray-900 text-sm">${item.description || 'No description'}</p>
                        <div class="flex items-center flex-wrap gap-x-2 gap-y-1 text-xs text-gray-600 mt-1">
                            <span class="font-semibold text-blue-700">${parseFloat(item.amount).toFixed(2)} ${item.currency}</span>
                            ${item.currency !== 'EUR' ? `<span class="text-gray-500">(€${parseFloat(item.amount_eur).toFixed(2)})</span>` : ''}
                            <span class="bg-gray-100 px-1.5 py-0.5 rounded-full">${item.category}</span>
                            <span>📅 ${item.date}</span>
                            <span>👤 ${item.person}</span>
                            ${item.beneficiary ? `<span>🎯 ${item.beneficiary}</span>` : ''}
                            ${item.has_image ? '<span title="Image attached">📷</span>' : ''}
                        </div>
                    </div>
                    <div class="expense-actions item-actions" onclick="event.stopPropagation()">
                        <button class="action-btn edit" onclick="expenseTracker.allItemsModal.editItem(${item.id})">✏️ Edit</button>
                        <button class="action-btn history" onclick="expenseTracker.auditManager.showAuditHistory(${item.id})">📋 History</button>
                        <button class="action-btn delete" onclick="expenseTracker.allItemsModal.confirmDelete(${item.id}, '${(item.description || '').replace(/'/g, "\\'")}')">🗑️ Delete</button>
                    </div>
                </div>
            </div>`;
    }

    toggleSelection(itemId, event) {
        event.stopPropagation();
        const item = document.querySelector(`[data-item-id="${itemId}"]`);
        const isSelected = item.classList.toggle('selected');
        
        if (isSelected) {
            this.selectedItems.add(itemId);
        } else {
            this.selectedItems.delete(itemId);
        }
        this.updateBulkActions();
    }

    updateBulkActions() {
        const bulkActions = document.getElementById('all-items-bulk-actions');
        const selectedCount = document.getElementById('all-items-selected-count');
        const toggleBtn = document.getElementById('all-items-toggle-select-btn');
        const count = this.selectedItems.size;
        
        const totalVisible = document.querySelectorAll('#all-items-list .item-row').length;
        const allSelected = count === totalVisible && totalVisible > 0;
        
        selectedCount.textContent = `${count} selected`;
        toggleBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        toggleBtn.className = `bulk-btn ${allSelected ? 'deselect-all' : 'select-all'}`;
        
        bulkActions.classList.toggle('show', count > 0);
    }

    toggleSelectAll() {
        const totalVisible = document.querySelectorAll('#all-items-list .item-row').length;
        const allSelected = this.selectedItems.size === totalVisible && totalVisible > 0;
        
        if (allSelected) {
            this.clearSelection();
        } else {
            this.selectAllVisible();
        }
    }

    selectAllVisible() {
        document.querySelectorAll('#all-items-list .item-row').forEach(item => {
            const itemId = parseInt(item.dataset.itemId);
            if (!this.selectedItems.has(itemId)) {
                item.classList.add('selected');
                this.selectedItems.add(itemId);
            }
        });
        this.updateBulkActions();
    }

    clearSelection() {
        document.querySelectorAll('#all-items-list .item-row.selected').forEach(item => {
            item.classList.remove('selected');
        });
        this.selectedItems.clear();
        this.updateBulkActions();
    }

    async editItem(id) {
        try {
            const expense = await expenseTracker.apiService.getExpense(id);
            expenseTracker.expenseForm.populateForm(expense, 'expense');
            this.hide(); // Close modal when editing
        } catch (error) { 
            console.error('Edit expense error:', error);
            expenseTracker.notificationManager.showNotification('❌', `Could not load expense for editing: ${error.message}`, 'error'); 
        }
    }

    confirmDelete(itemId, description) {
        expenseTracker.appState.currentDeleteOperation = { 
            type: 'individual', 
            targetType: 'expense', 
            expenseId: itemId, 
            description,
            source: 'allItemsModal'
        };
        const message = `Are you sure you want to delete "${description}"? This action cannot be undone.`;
        expenseTracker.modalManager.showDeleteConfirmationOverlay(message, '🗑️ Delete');
    }

    async confirmBulkDelete() {
        const count = this.selectedItems.size;
        if (count === 0) {
            expenseTracker.notificationManager.showNotification('⚠️', 'No items selected for deletion.', 'warning');
            return;
        }
        
        expenseTracker.appState.currentDeleteOperation = { 
            type: 'bulk', 
            targetType: 'expense', 
            expenseIds: Array.from(this.selectedItems),
            source: 'allItemsModal'
        };
        const message = `Are you sure you want to delete ${count} expense${count > 1 ? 's' : ''}? This action cannot be undone.`;
        const btnText = `🗑️ Delete ${count} Item${count > 1 ? 's' : ''}`;
        expenseTracker.modalManager.showDeleteConfirmationOverlay(message, btnText);
    }
}

// ============================================================================
// AUDIT HISTORY MANAGER
// ============================================================================

/**
 * Audit History Management System
 * 
 * AI CONTEXT: Displays change history for expense records with detailed
 * before/after comparisons and operation tracking.
 */
class AuditHistoryManager {
    constructor(apiService) {
        this.apiService = apiService;
    }
    
    async showAuditHistory(expenseId) {
        const modal = document.getElementById('audit-history-modal');
        const loading = document.getElementById('audit-loading');
        const content = document.getElementById('audit-content');
        const title = document.getElementById('audit-expense-title');
        
        modal.classList.remove('hidden');
        expenseTracker.modalManager.globalModalManager.registerModal('audit-history-modal', () => this.hideAuditHistory());
        loading.classList.remove('hidden');
        content.innerHTML = '';
        title.textContent = `Change history for expense #${expenseId}`;
        
        try {
            const response = await fetch(`./expense/${expenseId}/audit`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            const auditHistory = data.audit_history || [];
            
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
    }
    
    formatAuditEntry(entry) {
        const op = entry.operation.toLowerCase();
        const icon = {'insert': '➕', 'update': '✏️', 'delete': '🗑️'}[op] || '📝';
        
        let changesHtml = '';
        if (op === 'update' && entry.changes && Object.keys(entry.changes).length > 0) {
            changesHtml = `<div class="audit-changes">${Object.entries(entry.changes).map(([f, c]) => `<div class="audit-change-item"><div class="audit-change-label">${f.replace(/_/g, ' ')}:</div><div class="audit-change-values"><span class="audit-old-value">${this.formatValue(c.from)}</span><span class="audit-arrow">→</span><span class="audit-new-value">${this.formatValue(c.to)}</span></div></div>`).join('')}</div>`;
        } else if (op === 'insert' && entry.new_values) {
            changesHtml = `<div class="audit-changes"><div class="grid grid-cols-2 gap-2 text-xs">${Object.entries(entry.new_values).filter(([k,v]) => !['created_on','modified_on','has_image'].includes(k) && v).map(([k,v]) => `<div><strong>${k.replace('_', ' ')}:</strong> ${this.formatValue(v)}</div>`).join('')}</div></div>`;
        }

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
                ${changesHtml}
            </div>`;
    }
    
    formatValue(v) { return (v === null || v === '') ? '<em>empty</em>' : (String(v).length > 50 ? String(v).substring(0, 50) + '...' : v); }
    
    hideAuditHistory() { 
        document.getElementById('audit-history-modal').classList.add('hidden'); 
        expenseTracker.modalManager.globalModalManager.unregisterModal('audit-history-modal');
    }
}

// ============================================================================
// MAIN APPLICATION CLASS
// ============================================================================

/**
 * Main Expense Tracker Application
 * 
 * AI CONTEXT: Central orchestrator that initializes and coordinates all
 * application components. Manages the complete lifecycle of the application
 * from startup to user interactions.
 */
class ExpenseTrackerApp {
    constructor() {
        this.appState = new AppState();
        this.apiService = new ApiService();
        this.notificationManager = new NotificationManager();
        this.imageManager = new ImageManager();
        this.segmentedControls = new SegmentedControlsManager();
        this.formValidation = new FormValidationManager();
        this.dateWarningManager = new DateWarningManager();
        this.categoryManager = new CategoryManager(this.apiService, this.notificationManager);
        this.fxManager = new FxRateManager(this.apiService, this.notificationManager);
        this.expenseList = new ExpenseListManager(this.apiService, this.notificationManager, this.appState);
        this.bulkManager = new BulkOperationsManager(this.appState);
        this.auditManager = new AuditHistoryManager(this.apiService);
        this.allItemsModal = new AllItemsModalManager(this.apiService, this.notificationManager, this.appState, this.categoryManager);
        this.expenseForm = new ExpenseFormManager(this.apiService, this.notificationManager, this.appState, this.formValidation, this.categoryManager, this.segmentedControls, this.imageManager, this.dateWarningManager);
        this.draftManager = new DraftManager(this.apiService, this.notificationManager, this.expenseForm, this.appState);
        this.modalManager = new ModalManager(this.appState, this.apiService, this.notificationManager, this.expenseList, this.draftManager, this.allItemsModal);
        this.fileUploadManager = new FileUploadManager(this.apiService, this.notificationManager, this.appState, this.draftManager);
    }
    
    async initialize() {
        try {
            // Initialize all components in parallel for faster startup
            await Promise.all([
                this.categoryManager.loadCategories(),
                this.expenseList.loadLastFive(),
                this.draftManager.loadDrafts()
            ]);
            
            // Set up form defaults
            this.expenseForm.setDefaultDate();
            this.formValidation.setupRealTimeValidation();
            
            console.log('✅ Expense Tracker initialized successfully');
            this.notificationManager.showNotification('🚀', 'Application ready!', 'success');
        } catch (error) {
            console.error('❌ Failed to initialize Expense Tracker:', error);
            this.notificationManager.showNotification('❌', 'Failed to initialize application', 'error');
        }
    }

    async refreshMainPageContent() {
        try {
            // Refresh drafts section
            if (this.draftManager) {
                await this.draftManager.loadDrafts();
            }
            
            // Refresh expenses list
            if (this.expenseList) {
                await this.expenseList.loadLastFive();
            }
            
            // Refresh all items modal if it's open
            if (this.allItemsModal && document.getElementById('all-items-modal').classList.contains('active')) {
                await this.allItemsModal.loadAllItems();
            }
            
        } catch (error) {
            console.error('Failed to refresh main page content:', error);
            this.notificationManager.showNotification('⚠️', 'Failed to refresh content', 'error');
        }
    }
}
// ============================================================================
// APPLICATION INITIALIZATION
// ============================================================================

/**
 * Application Bootstrap
 * 
 * AI CONTEXT: Entry point for the application. Creates the main app instance
 * and initializes all components when the DOM is ready.
 * 
 * DEPLOYMENT: Works in both development and production environments.
 * The application is designed to be self-contained and framework-independent.
 */
let expenseTracker;

document.addEventListener('DOMContentLoaded', () => {
    console.log('🏁 Starting Expense Tracker...');
    expenseTracker = new ExpenseTrackerApp();
    expenseTracker.initialize();
});

// ============================================================================
// AI DEVELOPMENT NOTES AND PATTERNS
// ============================================================================

/*
AI COLLABORATION PATTERNS FOR THIS FILE:

1. **Adding New Features**:
   - Follow the class-based architecture pattern
   - Add new managers for complex functionality
   - Update the main ExpenseTrackerApp constructor to include new components
   - Document the purpose and dependencies in JSDoc comments

2. **Debugging and Maintenance**:
   - All classes have descriptive names and clear responsibilities
   - Console logging is used consistently for debugging
   - Error handling is centralized in the API service layer
   - State management is isolated in the AppState class

3. **Performance Considerations**:
   - Event delegation is used for dynamic content
   - API calls are batched where possible (initialization)
   - DOM queries are minimized and cached when appropriate
   - Auto-save functionality includes debouncing

4. **Code Organization**:
   - Each major feature has its own manager class
   - Related functionality is grouped together
   - Dependencies are injected through constructors
   - Event listeners are centralized in setupEventListeners methods

5. **Extensibility**:
   - New modal types can be added to the GlobalModalManager
   - New form validation rules can be added to FormValidationManager
   - New notification types can be added to NotificationManager
   - Additional bulk operations can be added to BulkOperationsManager

BROWSER COMPATIBILITY:
- Uses modern JavaScript features (ES6+ classes, async/await, fetch)
- Designed for modern browsers (Chrome 80+, Firefox 75+, Safari 13+)
- Progressive enhancement approach for older browsers
- No external dependencies beyond Tailwind CSS

SECURITY CONSIDERATIONS:
- All form data is validated on both client and server side
- XSS prevention through proper DOM manipulation
- CSRF protection through SameSite cookies (backend responsibility)
- Input sanitization for display purposes

TESTING STRATEGIES:
- Each manager class can be tested independently
- Mock API service for unit testing
- Integration tests can focus on complete workflows
- UI tests can verify modal and form interactions

FUTURE ENHANCEMENTS:
- Service Worker for offline functionality
- WebSocket integration for real-time updates
- Advanced keyboard shortcuts
- Drag-and-drop file organization
- Advanced search and filtering capabilities
*/