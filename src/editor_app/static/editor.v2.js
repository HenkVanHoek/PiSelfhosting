document.addEventListener('DOMContentLoaded', () => {
    const componentList = document.getElementById('component-list');
    const editorPane = document.getElementById('editor-pane');
    const feedbackAlert = document.getElementById('feedback-alert');
    const placeholder = document.getElementById('placeholder-text');
    const editorContent = document.getElementById('editor-content');

    let codeEditor = null;
    let currentVariables = [];

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
                showAlert('Template imported successfully!');
            };
            reader.onerror = () => showAlert('Error reading the file.', 'danger');
            reader.readAsText(file);
        };
    };

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
        manageBtn.addEventListener('click', () => {
            groupsList.innerHTML = '';
            if (!componentData || !componentData.groups) return;
            componentData.groups.forEach(group => {
                const isUsed = group.components.length > 0;
                const listItem = document.createElement('li');
                listItem.className = 'list-group-item d-flex justify-content-between align-items-center';
                listItem.innerHTML = `
                    <span>${group.name}</span>
                    <button class="btn btn-sm btn-outline-danger" data-group-id="${group.id}" ${isUsed ? 'disabled title="Cannot delete a group that contains components"' : ''}>
                        <i class="bi bi-trash"></i>
                    </button>
                `;
                groupsList.appendChild(listItem);
            });
            modal.show();
        });
        groupsList.addEventListener('click', async (e) => {
            const button = e.target.closest('button');
            if (!button || button.disabled) return;
            const groupId = button.dataset.groupId;
            if (confirm(`Are you sure you want to delete the group '${groupId}'? This cannot be undone.`)) {
                try {
                    await fetchJson(`/api/groups/${groupId}`, { method: 'DELETE' });
                    showAlert(`Group '${groupId}' deleted successfully.`, 'success');
                    modal.hide();
                    await loadComponents();
                } catch (error) {
                    showAlert(`Error deleting group: ${error.message}`, 'danger');
                }
            }
        });
    };

    const saveMetadata = async (componentId) => {
        const payload = {
            name: document.getElementById('comp-name').value,
            description: document.getElementById('comp-desc').value,
            group: document.getElementById('comp-group').value || null,
            depends_on: document.getElementById('comp-deps').value.split(',').map(s => s.trim()).filter(Boolean),
            has_ui: document.getElementById('comp-has-ui').checked,
            has_configuration: document.getElementById('comp-has-config').checked
        };
        const response = await fetch(`/api/components/${componentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error('Failed to save Core Metadata.');
    };

    const saveVariables = async (componentId) => {
        const payload = { variables: currentVariables };
        const response = await fetch(`/api/components/${componentId}/variables`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error('Failed to save User Variables.');
    };

    const saveTemplate = async (componentId) => {
        if (!codeEditor) return;
        const content = codeEditor.getValue();
        const response = await fetch(`/api/components/${componentId}/template`, {
            method: 'PUT',
            headers: { 'Content-Type': 'text/plain' },
            body: content
        });
        if (!response.ok) throw new Error('Failed to save Template Content.');
    };

    const handleSaveChanges = async (componentId) => {
        const saveButton = document.getElementById('save-changes-btn');
        saveButton.disabled = true;
        saveButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;
        try {
            await Promise.all([saveMetadata(componentId), saveVariables(componentId), saveTemplate(componentId)]);
            showAlert('All changes saved successfully!');
            await loadComponents();
        } catch (error) {
            console.error('Error saving changes:', error);
            showAlert(`Error: ${error.message}`, 'danger');
        } finally {
            saveButton.disabled = false;
            saveButton.innerHTML = 'Save All Changes';
        }
    };

    // --- NEW: Function to handle component deletion ---
    const handleDeleteComponent = async (componentId) => {
        if (confirm(`Are you sure you want to delete the component '${componentId}'? This action cannot be undone and will remove all associated files and data.`)) {
            try {
                await fetch(`/api/components/${componentId}`, { method: 'DELETE' });
                showAlert(`Component '${componentId}' deleted successfully!`, 'success');
                editorContent.classList.add('d-none');
                placeholder.classList.remove('d-none');
                await loadComponents();
            } catch (error) {
                showAlert(`Error deleting component: ${error.message}`, 'danger');
            }
        }
    };

    const renderVariablesPane = () => {
        const container = document.getElementById('variables-pane');
        container.innerHTML = `<div id="variables-list"></div><button class="btn btn-secondary mt-3" id="add-variable-btn"><i class="bi bi-plus-circle"></i> Add New Variable</button>`;
        const listContainer = document.getElementById('variables-list');
        const renderAllRows = () => {
            listContainer.innerHTML = '';
            if (currentVariables.length === 0) listContainer.innerHTML = '<p class="text-muted">No user variables defined.</p>';
            currentVariables.forEach((variable, index) => {
                const variableTypes = ['string', 'port', 'path'];
                const optionsHtml = variableTypes.map(type => `<option value="${type}" ${variable.type === type ? 'selected' : ''}>${type}</option>`).join('');
                const row = document.createElement('div');
                row.className = 'card mb-3';
                row.innerHTML = `
                    <div class="card-body">
                        <div class="row g-3">
                            <div class="col-md-6 col-lg-3"><label class="form-label">Variable ID</label><input type="text" class="form-control" data-index="${index}" data-field="id" value="${variable.id || ''}"></div>
                            <div class="col-md-6 col-lg-4"><label class="form-label">Description</label><input type="text" class="form-control" data-index="${index}" data-field="description" value="${variable.description || ''}"></div>
                            <div class="col-md-6 col-lg-2"><label class="form-label">Type</label><select class="form-select" data-index="${index}" data-field="type">${optionsHtml}</select></div>
                            <div class="col-md-6 col-lg-3"><label class="form-label">Default Value (Optional)</label><input type="text" class="form-control" data-index="${index}" data-field="default" value="${variable.default || ''}"></div>
                        </div>
                        <button class="btn btn-sm btn-outline-danger mt-3" data-index="${index}"><i class="bi bi-trash"></i> Remove</button>
                    </div>`;
                listContainer.appendChild(row);
            });
        };
        listContainer.addEventListener('change', e => {
            if (e.target.matches('input') || e.target.matches('select')) {
                const { index, field } = e.target.dataset;
                currentVariables[index][field] = e.target.value;
            }
        });
        listContainer.addEventListener('click', e => {
            if (e.target.matches('.btn-outline-danger, .btn-outline-danger *')) {
                const button = e.target.closest('button');
                currentVariables.splice(parseInt(button.dataset.index, 10), 1);
                renderAllRows();
            }
        });
        document.getElementById('add-variable-btn').addEventListener('click', () => {
            currentVariables.push({ id: '', description: '', type: 'string', default: '' });
            renderAllRows();
        });
        renderAllRows();
    };

    /**
     * @param {object} details
     * @param {string} details.id
     * @param {string} [details.name]
     * @param {string} [details.description]
     * @param {string} [details.group]
     * @param {string[]|string} [details.depends_on]
     * @param {boolean} [details.has_ui]
     * @param {boolean} [details.has_configuration]
     * @param {object[]} [details.required_variables]
     */
    const renderEditor = async (details) => {
        const componentId = details.id;
        currentVariables = details.required_variables || [];
        let dependsOn = Array.isArray(details.depends_on) ? details.depends_on : (details.depends_on ? [details.depends_on] : []);
        const dependsOnStr = dependsOn.join(', ');
        document.getElementById('editor-title').textContent = details.name || componentId;
        document.getElementById('metadata-pane').innerHTML = `
            <div class="mb-3"><label class="form-label">Component ID</label><input type="text" class="form-control" value="${componentId}" readonly></div>
            <div class="mb-3"><label for="comp-name" class="form-label">Name</label><input type="text" class="form-control" id="comp-name" value="${details.name || ''}"></div>
            <div class="mb-3"><label for="comp-desc" class="form-label">Description</label><textarea class="form-control" id="comp-desc" rows="3">${details.description || ''}</textarea></div>
            <div class="row">
                <div class="col-md-6 mb-3"><label for="comp-group" class="form-label">Group</label><input type="text" class="form-control"
                id="comp-group" list="group-datalist" value="${details.group || ''}"><datalist id="group-datalist"></datalist>
                </div>
                <div class="col-md-6 mb-3"><label for="comp-deps" class="form-label">Depends On</label><input type="text" class="form-control" id="comp-deps" value="${dependsOnStr}"></div>
            </div>
            <div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" role="switch" id="comp-has-ui"><label class="form-check-label" for="comp-has-ui">Has Web UI</label></div>
            <div class="form-check form-switch mb-3"><input class="form-check-input" type="checkbox" role="switch" id="comp-has-config"><label class="form-check-label" for="comp-has-config">Has User Configuration</label></div>`;
        const datalist = document.getElementById('group-datalist');
        datalist.innerHTML = '';
        if (componentData && componentData.groups) {
            componentData.groups.forEach(group => {
                const option = document.createElement('option');
                option.value = group.id;
                option.textContent = group.name;
                datalist.appendChild(option);
            });
        }
        document.getElementById('comp-has-ui').checked = details.has_ui || false;
        document.getElementById('comp-has-config').checked = details.has_configuration || false;
        document.getElementById('save-changes-btn').onclick = () => handleSaveChanges(componentId);
        document.getElementById('delete-component-btn').onclick = () => handleDeleteComponent(componentId);
        if (!codeEditor) {
            const selectedTheme = document.getElementById('theme-selector').value;
            codeEditor = CodeMirror.fromTextArea(document.getElementById('template-editor'), {
                lineNumbers: true,
                mode: 'yaml',
                theme: selectedTheme,
                tabSize: 2
            });
        }
        renderVariablesPane();
        setupEditorImportFeatures();
        placeholder.classList.add('d-none');
        editorContent.classList.remove('d-none');
        setTimeout(() => codeEditor.setSize("100%", "100%"), 50);
        await loadTemplateContent(componentId);
    };

    const loadTemplateContent = async (componentId) => {
        if (!codeEditor) return;
        try {
            const templateText = await fetchText(`/api/components/${componentId}/template`);
            codeEditor.setValue(templateText);
        } catch (error) {
            console.error(`Failed to load template for ${componentId}:`, error);
            codeEditor.setValue(`# Error: Failed to load template.\n# ${error.message}`);
        }
    };

    const loadComponentDetails = async (componentId) => {
        document.querySelectorAll('.component-list-item.active').forEach(item => item.classList.remove('active'));
        const selector = `.component-list-item[data-component-id="${componentId}"]`;
        document.querySelector(selector)?.classList.add('active');
        placeholder.classList.add('d-none');
        editorContent.classList.add('d-none');
        const loadingIndicator = document.getElementById('loading-indicator');
        if (!loadingIndicator) editorPane.insertAdjacentHTML('afterbegin', '<div id="loading-indicator" class="text-center text-muted"><p>Loading...</p></div>');
        try {
            const details = await fetchJson(`/api/components/${componentId}`);
            details.id = componentId;
            await renderEditor(details);
        } catch (error) {
            console.error('Error loading component details:', error);
            editorPane.innerHTML = `<p class="text-center text-danger">Failed to load details: ${error.message}</p>`;
        } finally {
            document.getElementById('loading-indicator')?.remove();
        }
    };

    const setupSortableGroups = () => {
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
            const sidebar = document.querySelector('.sidebar');
            if (!document.getElementById('component-search')) {
                const searchInput = document.createElement('div');
                searchInput.className = 'mb-3';
                searchInput.innerHTML = `<input type="text" id="component-search" class="form-control" placeholder="Search components...">`;
                sidebar.querySelector('.d-grid.gap-2.mb-3').insertAdjacentElement('afterend', searchInput);
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
                    loadComponentDetails(component.id);
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
                    if (group.is_exclusive) {
                        header.classList.add('group-header-exclusive');
                    }
                    groupContainer.appendChild(header);
                    const collapseWrapper = document.createElement('div');
                    collapseWrapper.id = groupId;
                    collapseWrapper.className = 'collapse show component-list-wrapper';
                    collapseWrapper.dataset.groupId = group.id;
                    group.components.forEach(comp => collapseWrapper.appendChild(createComponentLink(comp)));
                    groupContainer.appendChild(collapseWrapper);
                    componentList.appendChild(groupContainer);
                    new Sortable(collapseWrapper, {
                        group: 'shared-components',
                        animation: 150,
                        onEnd: (evt) => {
                           saveComponentOrder(evt.item, evt.from, evt.to);
                        }
                    });
                });
            }
        } catch (error) {
            console.error('Error loading components:', error);
            componentList.innerHTML = '<li class="list-group-item list-group-item-danger">Error loading components.</li>';
        }
    };

    (async () => {
        await loadComponents();
        setupThemeSelector();
        setupResizableSidebar();
        setupSortableGroups();
        setupCreateComponentModal();
        setupManageGroupsModal();
    })();
});
