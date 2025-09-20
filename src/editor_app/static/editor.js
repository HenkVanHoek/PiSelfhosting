document.addEventListener('DOMContentLoaded', () => {
    const componentList = document.getElementById('component-list');
    const editorPane = document.getElementById('editor-pane');
    const feedbackAlert = document.getElementById('feedback-alert');
    const placeholder = document.getElementById('placeholder-text');
    const editorContent = document.getElementById('editor-content');

    let codeEditor = null;
    let currentVariables = [];

    /** @type {object | null} */
    let componentData = null;

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
        feedbackAlert.className = `alert alert-${type} alert-dismissible fade show`;
        const closeButton = '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
        feedbackAlert.innerHTML = `${message}${closeButton}`;
        setTimeout(() => {
            const alertInstance = bootstrap.Alert.getOrCreateInstance(feedbackAlert);
            if (alertInstance) {
                alertInstance.close();
            }
        }, 5000);
    };

    const setupThemeSelector = () => {
        const themeSelector = document.getElementById('theme-selector');
        if (!themeSelector) return;

        // Load the saved theme from localStorage when the page loads
        const savedTheme = localStorage.getItem('editorTheme');
        if (savedTheme) {
            themeSelector.value = savedTheme;
        }

        // Listen for changes on the dropdown
        themeSelector.addEventListener('change', (event) => {
            const newTheme = event.target.value;

            // Save the newly chosen theme to localStorage
            localStorage.setItem('editorTheme', newTheme);

            if (codeEditor) {
                // Tell CodeMirror to use the new theme
                codeEditor.setOption('theme', newTheme);
            }
        });
    };

    const saveMetadata = async (componentId) => {
        const payload = {
            name: document.getElementById('comp-name').value,
            description: document.getElementById('comp-desc').value,
            uniqueness_group: document.getElementById('comp-group').value || null,
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

    const renderVariablesPane = () => {
        const container = document.getElementById('variables-pane');
        container.innerHTML = `<div id="variables-list"></div><button class="btn btn-secondary mt-3" id="add-variable-btn"><i class="bi bi-plus-circle"></i> Add New Variable</button>`;
        const listContainer = document.getElementById('variables-list');

        const renderAllRows = () => {
            listContainer.innerHTML = '';
            if (currentVariables.length === 0) {
                listContainer.innerHTML = '<p class="text-muted">No user variables defined.</p>';
            }
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

    /** @param {object} details */
    const renderEditor = async (details) => {
        const componentId = details.id;
        currentVariables = details.required_variables || [];
        let dependsOn = Array.isArray(details.depends_on) ? details.depends_on : (details.depends_on ? [details.depends_on] : []);
        const dependsOnStr = dependsOn.join(', ');

        document.getElementById('editor-title').textContent = details.name || componentId;
        document.getElementById('metadata-pane').innerHTML = `
            <div class="mb-3"><label for="comp-id" class="form-label">Component ID</label><input type="text" class="form-control" id="comp-id" value="${componentId}" readonly></div>
            <div class="mb-3"><label for="comp-name" class="form-label">Name</label><input type="text" class="form-control" id="comp-name" value="${details.name || ''}"></div>
            <div class="mb-3"><label for="comp-desc" class="form-label">Description</label><textarea class="form-control" id="comp-desc" rows="3">${details.description || ''}</textarea></div>
            <div class="row">
                <div class="col-md-6 mb-3"><label for="comp-group" class="form-label">Uniqueness Group</label><input type="text" class="form-control" id="comp-group" list="group-datalist" value="${details.uniqueness_group || ''}"><datalist id="group-datalist"></datalist></div>
                <div class="col-md-6 mb-3"><label for="comp-deps" class="form-label">Depends On (comma-separated)</label><input type="text" class="form-control" id="comp-deps" value="${dependsOnStr}"></div>
            </div>
            <div class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" role="switch" id="comp-has-ui"><label class="form-check-label" for="comp-has-ui">Has Web UI</label></div>
            <div class="form-check form-switch mb-3"><input class="form-check-input" type="checkbox" role="switch" id="comp-has-config"><label class="form-check-label" for="comp-has-config">Has User Configuration</label></div>`;

        const datalist = document.getElementById('group-datalist');
        datalist.innerHTML = '';
        if (componentData && componentData.groups) {
            componentData.groups.forEach(group => {
                const option = document.createElement('option');
                option.value = group.name;
                datalist.appendChild(option);
            });
        }

        document.getElementById('comp-has-ui').checked = details.has_ui || false;
        document.getElementById('comp-has-config').checked = details.has_configuration || false;
        document.getElementById('save-changes-btn').onclick = () => handleSaveChanges(componentId);

        if (!codeEditor) {
            const selectedTheme = document.getElementById('theme-selector').value;
            codeEditor = CodeMirror.fromTextArea(document.getElementById('template-editor'), { lineNumbers: true, mode: 'yaml', theme: selectedTheme, tabSize: 2 });
        }

        renderVariablesPane();
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
        if (!loadingIndicator) {
            editorPane.insertAdjacentHTML('afterbegin', '<div id="loading-indicator" class="text-center text-muted"><p>Loading...</p></div>');
        }

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
                    document.querySelectorAll('.component-list-item, .group-header, .ungrouped-header').forEach(el => {
                        const isHeader = el.classList.contains('group-header') || el.classList.contains('ungrouped-header');
                        const text = (isHeader ? el.dataset.groupName : el.textContent).toLowerCase();
                        const isVisible = text.includes(searchTerm);
                        el.style.display = isVisible ? '' : 'none';
                        if (isHeader && isVisible) {
                            // noinspection JSUnresolvedReference
                            document.querySelectorAll(el.dataset.bsTarget + ' .component-list-item').forEach(child => child.style.display = '');
                        }
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

            if (componentData.groups) {
                componentData.groups.forEach((group, index) => {
                    const groupId = `group-collapse-${index}`;
                    const header = document.createElement('a');
                    header.className = 'list-group-item list-group-item-secondary group-header d-flex justify-content-between align-items-center';
                    header.href = `#${groupId}`;
                    header.dataset.bsToggle = 'collapse';
                    header.dataset.groupName = group.name;
                    header.innerHTML = `<strong>${group.name}</strong> <i class="bi bi-chevron-down"></i>`;
                    componentList.appendChild(header);
                    const collapseWrapper = document.createElement('div');
                    collapseWrapper.id = groupId;
                    collapseWrapper.className = 'collapse show';
                    group.components.forEach(comp => collapseWrapper.appendChild(createComponentLink(comp)));
                    componentList.appendChild(collapseWrapper);
                });
            }

            if (componentData.ungrouped && componentData.ungrouped.length > 0) {
                const ungroupedHeader = document.createElement('div');
                ungroupedHeader.className = 'list-group-item list-group-item-light ungrouped-header mt-2';
                ungroupedHeader.dataset.groupName = 'ungrouped components';
                ungroupedHeader.textContent = 'Ungrouped Components';
                componentList.appendChild(ungroupedHeader);
                componentData.ungrouped.forEach(comp => componentList.appendChild(createComponentLink(comp)));
            }

        } catch (error) {
            console.error('Error loading components:', error);
            componentList.innerHTML = '<li class="list-group-item list-group-item-danger">Error loading components.</li>';
        }
    };

    (async () => {
        await loadComponents();
        setupThemeSelector();
    })();
});
