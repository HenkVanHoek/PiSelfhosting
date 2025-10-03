// src/editor_app/static/editor.v2.js

import { renderEditor, renderVariablesPane } from './ui_render_utils.js';

document.addEventListener('DOMContentLoaded', () => {
    const componentList = document.getElementById('component-list');
    const editorPane = document.getElementById('editor-pane');
    const feedbackAlert = document.getElementById('feedback-alert');
    const placeholder = document.getElementById('placeholder-text');
    const editorContent = document.getElementById('editor-content');
    const saveChangesBtn = document.getElementById('save-changes-btn');
    const discardChangesBtn = document.getElementById('discard-changes-btn');
    const editorTabs = document.querySelectorAll('#editorTabs button[data-bs-toggle="tab"]');

    let codeEditor = null;
    let currentVariables = [];
    let internalRenderVariablesRows = null; // Stores the inner render function from ui_render_utils

    /**
     * @typedef {object} ComponentSummary
     * @property {string} id
     * @property {string} name
     */
    /**
     * @typedef {object} Group
     * @property {string} id
     * @property {string} name
     * @property {boolean} is_exclusive
     * @property {ComponentSummary[]} components
     */
    /**
     * @typedef {object} ComponentData
     * @property {Group[]} groups
     */
    /** @type {ComponentData | null} */
    let componentData = null;

    /**
     * @typedef {object} ComponentVariable
     * @property {string} id
     * @property {string} [label]
     * @property {string} description
     * @property {string} type
     * @property {string} [default]
     * @property {'always'|'clean-install'|''} [required]
     * @property {'dotenv'} [source]
     */

    const dirtyTabs = new Set();
    let nextTabTarget = null;
    const unsavedChangesModal = new bootstrap.Modal(document.getElementById('unsavedChangesModal'));

    const updateUiForDirtyState = () => {
        const isDirty = dirtyTabs.size > 0;
        saveChangesBtn.disabled = !isDirty;
        if (isDirty) {
            discardChangesBtn.classList.remove('d-none');
        } else {
            discardChangesBtn.classList.add('d-none');
        }
        editorTabs.forEach(tabButton => {
            const paneId = tabButton.getAttribute('data-bs-target').substring(1);
            if (dirtyTabs.has(paneId)) {
                tabButton.classList.add('tab-dirty');
            } else {
                tabButton.classList.remove('tab-dirty');
            }
        });
    };

    const markTabAsDirty = (paneId) => {
        dirtyTabs.add(paneId);
        updateUiForDirtyState();
    };

    const clearAllDirtyState = () => {
        dirtyTabs.clear();
        updateUiForDirtyState();
    };

    const collectVariablesFromDOM = () => {
        const newVariables = [];
        const rows = document.querySelectorAll('#variables-list .card');
        rows.forEach(row => {
            const idEl = row.querySelector('[data-field="id"]');
            // CRITICAL FIX: Add defensive checks for all variable fields.
            // If querySelector returns null, accessing .value throws a TypeError.
            const labelEl = row.querySelector('[data-field="label"]');
            const descEl = row.querySelector('[data-field="description"]');
            const typeEl = row.querySelector('[data-field="type"]');
            const sourceEl = row.querySelector('[data-field="source"]');
            const defaultEl = row.querySelector('[data-field="default"]');
            const requiredEl = row.querySelector('[data-field="required"]');

            if (idEl && idEl.value) {
                newVariables.push({
                    id: idEl.value,
                    label: labelEl ? labelEl.value : '',
                    description: descEl ? descEl.value : '',
                    type: typeEl ? typeEl.value : 'text', // Default to 'text' if missing
                    source: sourceEl ? sourceEl.value : '',
                    default: defaultEl ? defaultEl.value : '',
                    required: requiredEl ? requiredEl.value : ''
                });
            }
        });
        return newVariables;
    };

    // --- Utility Functions ---

    async function fetchJson(url, options = {}) {
        const response = await fetch(url, options);
        if (!response.ok) {
            let errorMsg = `Request failed with status ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.error || errorMsg;
            } catch (e) { /* Ignore non-JSON errors */
            }
            throw new Error(errorMsg);
        }
        return response.json();
    }

    async function fetchText(url, options = {}) {
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }
        return response.text();
    }

    const showAlert = (message, type = 'success') => {
        if (!feedbackAlert) {
            console.error('Feedback alert element not found');
            return;
        }
        feedbackAlert.className = `alert alert-${type} alert-dismissible fade show`;
        const closeButton = '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
        feedbackAlert.innerHTML = `${message}${closeButton}`;
        setTimeout(() => {
            const alertInstance = bootstrap.Alert.getOrCreateInstance(feedbackAlert);
            if (alertInstance) alertInstance.close();
        }, 5000);
    };

    // --- Save Handlers (Including Conflict Gatekeeper) ---

    const saveMetadata = async (componentId) => {
        const portInput = document.getElementById('comp-traefik-port');
        const payload = {
            name: document.getElementById('comp-name').value,
            description: document.getElementById('comp-desc').value,
            group: document.getElementById('comp-group').value || null,
            depends_on: document.getElementById('comp-deps').value.split(',').map(s => s.trim()).filter(Boolean),
            conflicts_with: document.getElementById('comp-conflicts').value.split(',').map(s => s.trim()).filter(Boolean),
            has_ui: document.getElementById('comp-has-ui').checked,
            has_configuration: document.getElementById('comp-has-config').checked,
            has_traefik_support: document.getElementById('comp-has-traefik').checked,
            // Ensure we send a valid number or null
            traefik_internal_port: portInput.disabled ? null : parseInt(portInput.value) || null
        };
        await fetchJson(`/api/components/${componentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    };

    const saveVariables = async (componentId) => {
        // This relies on the fix to collectVariablesFromDOM being present
        const payload = { variables: collectVariablesFromDOM() };
        await fetchJson(`/api/components/${componentId}/variables`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    };

    const saveTemplate = async (componentId) => {
        if (!codeEditor) return;
        const content = codeEditor.getValue();
        await fetchText(`/api/components/${componentId}/template`, {
            method: 'PUT',
            headers: { 'Content-Type': 'text/plain' },
            body: content
        });
    };

    /**
     * CRITICAL: Calls the new backend API endpoint to validate the conflicts_with list.
     * This relies on the already-tested Python logic for correctness.
     * @param {string} componentId - The ID of the component being saved.
     * @returns {Promise<boolean>} - True if validation succeeded (200), False otherwise (400).
     */
    const runConflictGatekeeper = async (componentId) => {
        const conflictsWithList = document.getElementById('comp-conflicts').value
            .split(',')
            .map(s => s.trim())
            .filter(Boolean);

        try {
            // New dedicated validation API call
            await fetchJson(`/api/components/${componentId}/validate_metadata_conflicts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conflicts_with: conflictsWithList })
            });

            // If the API returns 200, validation is successful
            return true;
        } catch (error) {
            // The API returns a 400 with the specific error message from ComponentManager
            showAlert(`Conflict Validation Failed: ${error.message}`, 'danger');
            return false;
        }
    };

    const handleSaveChanges = async (componentId) => {
        saveChangesBtn.disabled = true;
        saveChangesBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;

        try {
            // CRITICAL STEP: Run the new conflict gatekeeper before saving
            if (!(await runConflictGatekeeper(componentId))) {
                return; // Stop the save process if the gatekeeper fails
            }

            // Save is atomic after validation passes
            await Promise.all([saveMetadata(componentId), saveVariables(componentId), saveTemplate(componentId)]);
            showAlert('All changes saved successfully!', 'success');
            clearAllDirtyState();
            await loadComponents();
            const selector = `.component-list-item[data-component-id="${componentId}"]`;
            document.querySelector(selector)?.classList.add('active');
        } catch (error) {
            console.error('Error saving changes:', error);
            showAlert(`Error: ${error.message}`, 'danger');
        } finally {
            saveChangesBtn.innerHTML = '<i class="bi bi-save"></i> Save All Changes';
            updateUiForDirtyState();
        }
    };

    const runValidation = async (componentId) => {
        const validateBtn = document.getElementById('validate-template-btn');
        if (validateBtn) {
            validateBtn.disabled = true;
            validateBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Validating...`;
        }

        const variablesFromDOM = collectVariablesFromDOM();
        const validVariables = variablesFromDOM.filter(v => v.id && v.id.trim() !== '');

        const payload = {
            template_content: codeEditor ? codeEditor.getValue() : "",
            variables: validVariables
        };

        try {
            const response = await fetchJson(`/api/components/${componentId}/validate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            showAlert(response.message, 'success');
            return true;
        } catch (error) {
            showAlert(error.message, 'danger');
            return false;
        } finally {
            if (validateBtn) {
                validateBtn.disabled = false;
                validateBtn.innerHTML = `<i class="bi bi-check-circle"></i> Validate Template`;
            }
        }
    };


    const handleDeleteComponent = async (componentId) => {
        if (confirm(`Are you sure you want to delete the component '${componentId}'? This action cannot be undone and will remove all associated files and data.`)) {
            try {
                await fetch(`/api/components/${componentId}`, { method: 'DELETE' });
                showAlert(`Component '${componentId}' deleted successfully!`, 'success');
                editorContent.classList.add('d-none');
                placeholder.classList.remove('d-none');
                await loadComponents();
            } catch (error)
            {
                showAlert(`Error deleting component: ${error.message}`, 'danger');
            }
        }
    };

    // --- Variables Pane Handlers ---

    /**
     * Handles the state mutation for the variables pane and triggers a re-render.
     * @param {number|undefined} [indexToRemove] - Optional index of a variable to remove.
     */
    const handleVariablesStateAndRender = (indexToRemove) => {
        // If an index is provided, mutate the array
        if (indexToRemove !== undefined) {
            currentVariables.splice(indexToRemove, 1);
        }

        if (internalRenderVariablesRows) {
            internalRenderVariablesRows();
        }
    };

    const handleAddVariable = () => {
        currentVariables.push({ id: '', label: '', description: '', type: 'text', source: '', default: '', required: '' });
        handleVariablesStateAndRender();
        markTabAsDirty('variables-pane');
    };

    // --- Component Loading & Rendering ---

    /**
     * @param {object} details - The component details object from the API.
     * @param {string} details.id
     * @param {string[]|string} [details.conflicts_with]
     * @param {ComponentVariable[]} [details.required_variables]
     */
    const applicationRenderEditor = async (details) => {
        const componentId = details.id;
        currentVariables = details.required_variables || [];

        // 1. Render Metadata
        renderEditor(
            details,
            componentData,
            markTabAsDirty,
            handleSaveChanges,
            handleDeleteComponent
        );

        // 2. Render Variables Pane
        internalRenderVariablesRows = renderVariablesPane({
            variables: currentVariables,
            renderAllRowsCallback: handleVariablesStateAndRender,
            markTabDirtyCallback: () => markTabAsDirty('variables-pane'),
            onAddVariable: handleAddVariable, // Pass the handler
        });

        const addVariableBtn = document.getElementById('add-variable-btn');
        if (addVariableBtn) {
            // FIX: Re-attach the handler cleanly to fix potential regression where
            // the button event logic was relying on a dynamically attached handler
            // inside renderVariablesPane that might not be firing correctly.
            addVariableBtn.onclick = handleAddVariable;
        }

        // 3. Setup CodeMirror
        if (!codeEditor) {
            const selectedTheme = document.getElementById('theme-selector').value;
            codeEditor = CodeMirror.fromTextArea(document.getElementById('template-editor'), {
                lineNumbers: true, mode: 'yaml', theme: selectedTheme, tabSize: 2
            });
        }
        if (codeEditor.dirtyMarker) codeEditor.off('change', codeEditor.dirtyMarker);
        const dirtyMarker = () => markTabAsDirty('template-pane');
        codeEditor.on('change', dirtyMarker);
        codeEditor.dirtyMarker = dirtyMarker;

        // 4. Final Setup
        setupEditorImportFeatures();

        const validateBtn = document.getElementById('validate-template-btn');
        if (validateBtn) {
            validateBtn.onclick = () => runValidation(componentId);
        }

        placeholder.classList.add('d-none');
        editorContent.classList.remove('d-none');
        setTimeout(() => codeEditor.setSize("100%", "100%"), 50);
        await loadTemplateContent(componentId);
    };

    const loadTemplateContent = async (componentId) => {
        if (!codeEditor) return;

        if (codeEditor.dirtyMarker) codeEditor.off('change', codeEditor.dirtyMarker);

        try {
            const templateText = await fetchText(`/api/components/${componentId}/template`);
            codeEditor.setValue(templateText);
        } catch (error) {
            console.error(`Failed to load template for ${componentId}:`, error);
            codeEditor.setValue(`# Error: Failed to load template.\n# ${error.message}`);
        } finally {
            if (codeEditor.dirtyMarker) codeEditor.on('change', codeEditor.dirtyMarker);
        }
    };

    const loadComponentDetails = async (componentId, force = false) => {
        if (dirtyTabs.size > 0 && !force) {
            if (!confirm('You have unsaved changes that will be lost. Are you sure you want to load a new component?')) {
                return;
            }
        }
        clearAllDirtyState();

        document.querySelectorAll('.component-list-item.active').forEach(item => item.classList.remove('active'));
        const selector = `.component-list-item[data-component-id="${componentId}"]`;
        document.querySelector(selector)?.classList.add('active');
        placeholder.classList.add('d-none');
        editorContent.classList.add('d-none');
        if (!document.getElementById('loading-indicator')) {
            editorPane.insertAdjacentHTML('afterbegin', '<div id="loading-indicator" class="text-center text-muted"><p>Loading...</p></div>');
        }
        try {
            const details = await fetchJson(`/api/components/${componentId}`);
            details.id = componentId;
            await applicationRenderEditor(details);
        } catch (error) {
            console.error('Error loading component details:', error);
            editorPane.innerHTML = `<p class="text-center text-danger">Failed to load details: ${error.message}</p>`;
        } finally {
            document.getElementById('loading-indicator')?.remove();
            clearAllDirtyState();
        }
    };

    // --- Setup & Lifecycle Functions (Cleaned) ---

    // (runValidation is defined above for scope, though it was in the original context)

    const setupResizableSidebar = () => {
        const sidebar = document.getElementById('sidebar');
        const handle = document.getElementById('drag-handle');
        if (!sidebar || !handle) return;
        const savedWidth = localStorage.getItem('sidebarWidth');
        if (savedWidth) {
            sidebar.style.width = `${savedWidth}px`;
        }
        let isResizing = false;
        handle.addEventListener('mousedown', () => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
        const onMouseMove = (e) => {
            if (!isResizing) return;
            const minWidth = parseInt(getComputedStyle(sidebar).minWidth, 10);
            const maxWidth = parseInt(getComputedStyle(sidebar).maxWidth, 10);
            let newWidth = e.clientX;
            if (newWidth < minWidth) newWidth = minWidth;
            if (newWidth > maxWidth) newWidth = maxWidth;
            sidebar.style.width = newWidth.toString() + 'px';
        };
        const onMouseUp = () => {
            isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            localStorage.setItem('sidebarWidth', sidebar.offsetWidth.toString());
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };
    };

    const setupEditorImportFeatures = () => {
        const editorWrapper = document.getElementById('editor-wrapper');
        const importBtn = document.getElementById('import-template-btn');
        const fileInput = document.getElementById('template-file-input');
        if (!editorWrapper || !importBtn || !fileInput || !codeEditor) return;
        importBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) handleFile(file);
        });
        editorWrapper.addEventListener('dragover', (e) => {
            e.preventDefault();
            editorWrapper.classList.add('drag-over');
        });
        editorWrapper.addEventListener('dragleave', () => editorWrapper.classList.remove('drag-over'));
        editorWrapper.addEventListener('drop', (e) => {
            e.preventDefault();
            editorWrapper.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
        });
        const handleFile = (file) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                codeEditor.setValue(e.target.result);
                markTabAsDirty('template-pane');
                showAlert('Template imported successfully!');
            };
            reader.onerror = () => showAlert('Error reading the file.', 'danger');
            reader.readAsText(file);
        };
    };

    const setupThemeSelector = () => {
        const themeSelector = document.getElementById('theme-selector');
        if (!themeSelector) return;
        const savedTheme = localStorage.getItem('editorTheme');
        if (savedTheme) themeSelector.value = savedTheme;
        themeSelector.addEventListener('change', (event) => {
            const newTheme = event.target.value;
            localStorage.setItem('editorTheme', newTheme);
            if (codeEditor) codeEditor.setOption('theme', newTheme);
        });
    };

    const setupCreateComponentModal = () => {
        const createBtn = document.getElementById('create-new-btn');
        const modalElement = document.getElementById('create-component-modal');
        if (!createBtn || !modalElement) return;
        const modal = new bootstrap.Modal(modalElement);
        const form = document.getElementById('create-component-form');

        if (!form) {
            console.error('Create component form not found in the DOM.');
            return;
        }

        const compIdInput = document.getElementById('new-component-id-input');
        const compNameInput = document.getElementById('new-component-name');
        createBtn.addEventListener('click', () => {
            form.reset();
            modal.show();
        });
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const componentId = compIdInput.value.trim();
            const componentName = compNameInput.value.trim();
            const validIdPattern = /^[a-z0-9-]+$/;
            if (!validIdPattern.test(componentId)) {
                showAlert('Invalid Component ID. Use only lowercase letters, numbers, and hyphens.', 'warning');
                compIdInput.classList.add('is-invalid');
                return;
            }
            compIdInput.classList.remove('is-invalid');
            if (!componentName) {
                showAlert('Component Name is required.', 'warning');
                return;
            }
            try {
                await fetchJson('/api/components', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: componentId, name: componentName })
                });
                showAlert(`Component '${componentName}' created successfully!`, 'success');
                modal.hide();
                await loadComponents();
            } catch (error) {
                showAlert(`Error creating component: ${error.message}`, 'danger');
            }
        });
    };

    const setupManageGroupsModal = () => {
        const manageBtn = document.getElementById('manage-groups-btn');
        const modalElement = document.getElementById('manage-groups-modal');
        if (!manageBtn || !modalElement) return;
        const modal = new bootstrap.Modal(modalElement);
        const groupsList = document.getElementById('manage-groups-list');
        if (!groupsList) {
            console.error('Manage groups list not found in the DOM.');
            return;
        }
        manageBtn.addEventListener('click', () => {
            groupsList.innerHTML = '';
            if (!componentData || !componentData.groups) return;
            componentData.groups.forEach(group => {
                const isUsed = group.components.length > 0;
                const listItem = document.createElement('li');
                listItem.className = 'list-group-item d-flex justify-content-between align-items-center';
                listItem.innerHTML = `
                    <div class="flex-grow-1 me-2">
                        <span class="group-name-display">${group.name}</span>
                        <input type="text" class="form-control d-none group-name-input" value="${group.name}">
                    </div>
                    <div>
                        <button class="btn btn-sm btn-outline-primary me-1" data-action="edit"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline-success d-none me-1" data-action="save"><i class="bi bi-check-lg"></i></button>
                        <button class="btn btn-sm btn-outline-danger" data-action="delete" data-group-id="${group.id}" ${isUsed ? 'disabled title="Cannot delete a group that contains components"' : ''}>
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                `;
                groupsList.appendChild(listItem);
            });
            modal.show();
        });
        groupsList.addEventListener('click', async (e) => {
            const button = e.target.closest('button');
            if (!button) return;
            const action = button.dataset.action;
            const listItem = button.closest('li');
            const groupNameDisplay = listItem.querySelector('.group-name-display');
            const groupNameInput = listItem.querySelector('.group-name-input');
            const editBtn = listItem.querySelector('[data-action="edit"]');
            const saveBtn = listItem.querySelector('[data-action="save"]');
            const deleteBtn = listItem.querySelector('[data-action="delete"]');
            const groupId = deleteBtn.dataset.groupId;

            if (action === 'edit') {
                groupNameDisplay.classList.add('d-none');
                groupNameInput.classList.remove('d-none');
                editBtn.classList.add('d-none');
                saveBtn.classList.remove('d-none');
                groupNameInput.focus();
            } else if (action === 'save') {
                const newName = groupNameInput.value.trim();
                if (newName && newName !== groupNameDisplay.textContent) {
                    try {
                        await fetchJson(`/api/groups/${groupId}/rename`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ name: newName })
                        });
                        showAlert(`Group renamed to '${newName}' successfully!`, 'success');
                        modal.hide();
                        await loadComponents();
                    } catch (error) {
                        showAlert(`Error renaming group: ${error.message}`, 'danger');
                    }
                } else {
                    groupNameDisplay.classList.remove('d-none');
                    groupNameInput.classList.add('d-none');
                    editBtn.classList.remove('d-none');
                    saveBtn.classList.add('d-none');
                }
            } else if (action === 'delete') {
                if (button.disabled) return;
                if (confirm(`Are you sure you want to delete the group '${groupId}'? This cannot be undone.`)) {
                    try {
                        await fetchJson(`/api/groups/${groupId}`, { method: 'DELETE' });
                        showAlert(`Group '${groupId}' deleted successfully!`, 'success');
                        modal.hide();
                        await loadComponents();
                    } catch (error) {
                        showAlert(`Error deleting group: ${error.message}`, 'danger');
                    }
                }
            }
        });
    };

    const setupHashGenerator = () => {
        const hashGeneratorModalEl = document.getElementById('hashGeneratorModal');
        const hashGeneratorForm = document.getElementById('hash-generator-form');
        const hashUsernameInput = document.getElementById('hash-username');
        const hashPasswordInput = document.getElementById('hash-password');
        const hashPasswordConfirmInput = document.getElementById('hash-password-confirm');
        const passwordMatchFeedback = document.getElementById('password-match-feedback');
        const generateHashSubmitBtn = document.getElementById('generate-hash-submit-btn');
        const hashResultArea = document.getElementById('hash-result-area');
        const hashOutputInput = document.getElementById('hash-output');
        const copyHashBtn = document.getElementById('copy-hash-btn');
        const generateHashBtn = document.getElementById('generate-hash-btn');

        if (!hashGeneratorModalEl || !generateHashBtn) return;

        const hashGeneratorModal = new bootstrap.Modal(hashGeneratorModalEl);

        generateHashBtn.addEventListener('click', () => {
            hashGeneratorForm.reset();
            hashPasswordInput.classList.remove('is-invalid');
            hashPasswordConfirmInput.classList.remove('is-invalid');
            hashResultArea.style.display = 'none';
            hashGeneratorModal.show();
        });

        hashGeneratorForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const username = hashUsernameInput.value.trim();
            const password = hashPasswordInput.value;
            const passwordConfirm = hashPasswordConfirmInput.value;

            if (password !== passwordConfirm) {
                hashPasswordInput.classList.add('is-invalid');
                hashPasswordConfirmInput.classList.add('is-invalid');
                passwordMatchFeedback.style.display = 'block';
                showAlert('Passwords do not match.', 'danger');
                return;
            }
            hashPasswordInput.classList.remove('is-invalid');
            hashPasswordConfirmInput.classList.remove('is-invalid');
            passwordMatchFeedback.style.display = 'none';

            if (!username || !password) {
                showAlert('Username and Password cannot be empty.', 'danger');
                return;
            }

            generateHashSubmitBtn.disabled = true;
            generateHashSubmitBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Generating...`;

            try {
                const payload = { username, password };
                const response = await fetchJson('/api/generate_auth_hash', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                // noinspection JSUnresolvedVariable
                hashOutputInput.value = response.hashed_user_string;
                hashResultArea.style.display = 'block';
                showAlert('Secure hash generated successfully!', 'success');

            } catch (error) {
                showAlert(`Error generating hash: ${error.message}`, 'danger');
                hashResultArea.style.display = 'none';
            } finally {
                generateHashSubmitBtn.disabled = false;
                generateHashSubmitBtn.innerHTML = `Generate Hash`;
            }
        });

        copyHashBtn.addEventListener('click', async () => {
            const textToCopy = hashOutputInput.value;
            try {
                await navigator.clipboard.writeText(textToCopy);
                showAlert('Hash string copied to clipboard!', 'success');
            } catch (err) {
                // Fallback for older browsers
                hashOutputInput.select();
                // noinspection JSDeprecatedSymbols
                document.execCommand('copy');
                showAlert('Hash string copied to clipboard (Legacy fallback)!', 'success');
            }
        });
    };

    const setupSortableGroups = () => {
        // CRITICAL FIX: Add defensive check for Sortable library existence
        if (typeof Sortable === 'undefined') {
            console.error('Sortable.js library not loaded. Cannot set up group sorting.');
            return;
        }
        new Sortable(componentList, {
            animation: 150,
            handle: '.group-header',
            onEnd: async () => {
                const newOrder = Array.from(componentList.querySelectorAll('.group-header'))
                    .map(header => header.dataset.groupId);
                try {
                    await fetchJson('/api/groups/order', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(newOrder)
                    });
                    showAlert('Group order saved!');
                } catch (error) {
                    showAlert(`Error saving group order: ${error.message}`, 'danger');
                }
            }
        });
    };

    const saveComponentOrder = async (movedItem, fromGroup, toGroup) => {
        const componentId = movedItem.dataset.componentId;
        const fromGroupId = fromGroup.dataset.groupId;
        const toGroupId = toGroup.dataset.groupId;
        if (fromGroupId !== toGroupId) {
            try {
                await fetchJson(`/api/components/${componentId}/group`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({group: toGroupId})
                });
                 showAlert(`Moved ${componentId} to group ${toGroupId}`);
            } catch (error) {
                showAlert(`Error moving component: ${error.message}`, 'danger');
                await loadComponents();
                return;
            }
        }
        const allComponentItems = document.querySelectorAll('.component-list-item');
        const newOrder = Array.from(allComponentItems).map(item => item.dataset.componentId);
        try {
            await fetchJson('/api/components/order', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(newOrder)
            });
            if (fromGroupId === toGroupId) {
                console.log('Component order saved');
            }
        } catch (error) {
            showAlert(`Error saving component order: ${error.message}`, 'danger');
        }
    };

    const loadComponents = async () => {
        try {
            componentData = await fetchJson('/api/components');
            const sidebarControls = document.getElementById('sidebar-controls');
            if (!document.getElementById('component-search')) {
                const searchInput = document.createElement('div');
                searchInput.innerHTML = `<input type="text" id="component-search" class="form-control" placeholder="Search components...">`;
                sidebarControls.appendChild(searchInput);
                searchInput.addEventListener('input', (e) => {
                    const searchTerm = e.target.value.toLowerCase();
                    document.querySelectorAll('.group-container').forEach(container => {
                        const headerText = container.querySelector('.group-header').dataset.groupId.toLowerCase();
                        const itemsText = Array.from(container.querySelectorAll('.component-list-item'))
                            .map(item => item.textContent.toLowerCase())
                            .join(' ');
                        const isVisible = headerText.includes(searchTerm) || itemsText.includes(searchTerm);
                        container.style.display = isVisible ? '' : 'none';
                    });
                });
            }
            componentList.innerHTML = '';
            const createComponentLink = (component) => {
                const link = document.createElement('a');
                link.href = '#';
                link.className = 'list-group-item list-group-item-action component-list-item';
                link.textContent = component.name || component.id;
                link.dataset.componentId = component.id;
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    void loadComponentDetails(component.id, false);
                });
                return link;
            };
            if (componentData && componentData.groups) {
                componentData.groups.forEach(group => {
                    const groupContainer = document.createElement('div');
                    groupContainer.className = 'group-container mb-2';
                    const groupId = `group-collapse-${group.id}`;
                    const header = document.createElement('a');
                    header.className = 'list-group-item list-group-item-secondary group-header d-flex justify-content-between align-items-center';
                    header.href = `#${groupId}`;
                    header.dataset.bsToggle = 'collapse';
                    header.dataset.groupId = group.id;
                    header.innerHTML = `<strong>${group.name}</strong> <i class="bi bi-chevron-down"></i>`;
                    if (group.is_exclusive) header.classList.add('group-header-exclusive');
                    groupContainer.appendChild(header);
                    const collapseWrapper = document.createElement('div');
                    collapseWrapper.id = groupId;
                    collapseWrapper.className = 'collapse show component-list-wrapper';
                    collapseWrapper.dataset.groupId = group.id;
                    group.components.forEach(comp => collapseWrapper.appendChild(createComponentLink(comp)));
                    groupContainer.appendChild(collapseWrapper);
                    componentList.appendChild(groupContainer);
                    // CRITICAL FIX: Add defensive check for Sortable library existence
                    if (typeof Sortable !== 'undefined') {
                        new Sortable(collapseWrapper, {
                            group: 'shared-components',
                            animation: 150,
                            onEnd: (evt) => {
                               saveComponentOrder(evt.item, evt.from, evt.to);
                            }
                        });
                    }
                });
            }
        } catch (error) {
            console.error('Error loading components:', error);
            componentList.innerHTML = '<li class="list-group-item list-group-item-danger">Error loading components.</li>';
        }
    };

    const setupDirtyFormHandling = () => {
        editorTabs.forEach(tab => {
            tab.addEventListener('show.bs.tab', (event) => {
                if (dirtyTabs.size > 0) {
                    event.preventDefault();
                    nextTabTarget = event.target;
                    unsavedChangesModal.show();
                }
            });
        });

        document.getElementById('discard-and-continue-btn').addEventListener('click', () => {
            clearAllDirtyState();
            unsavedChangesModal.hide();
            if (nextTabTarget) {
                new bootstrap.Tab(nextTabTarget).show();
                nextTabTarget = null;
            }
        });

        document.getElementById('save-and-continue-btn').addEventListener('click', async () => {
            const componentId = document.getElementById('comp-id').value;
            await handleSaveChanges(componentId);
            unsavedChangesModal.hide();
            if (dirtyTabs.size === 0 && nextTabTarget) {
                new bootstrap.Tab(nextTabTarget).show();
                nextTabTarget = null;
            }
        });

        discardChangesBtn.addEventListener('click', () => {
            const componentId = document.getElementById('comp-id').value;
            if (componentId) {
                void loadComponentDetails(componentId, true);
            }
        });
    };

    // --- Main Initialization ---

    (async () => {
        await loadComponents();
        setupThemeSelector();
        setupResizableSidebar();
        setupSortableGroups();
        setupCreateComponentModal();
        setupManageGroupsModal();
        setupDirtyFormHandling();
        setupHashGenerator();
        updateUiForDirtyState();
    })();
});
