/**
 * @fileoverview Utility functions for rendering the PiSelfhosting Editor UI.
 * This file contains DOM creation and manipulation logic, separated from core
 * application state and API interaction logic.
 */

// Define the mandatory and supported variable types and sources for the UI
const VARIABLE_TYPES = ['string', 'port', 'path', 'password'];
const VARIABLE_SOURCES = [
    { value: '', label: 'User Input' },
    { value: 'dotenv', label: 'DotEnv' }
];
const VARIABLE_REQUIRED_OPTIONS = [
    { value: '', label: 'Not Required' },
    { value: 'always', label: 'Required Always' },
    { value: 'clean-install', label: 'Required on Clean Install' }
];

/**
 * Creates a standard HTML option element.
 * @param {string} value - The option value.
 * @param {string} text - The option display text.
 * @param {boolean} isSelected - Whether the option should be pre-selected.
 * @returns {HTMLOptionElement}
 */
const createOption = (value, text, isSelected) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = text;
    if (isSelected) {
        option.selected = true;
    }
    return option;
};

/**
 * Creates an input, select, or textarea element for a variable field.
 * @param {string} tag - The HTML tag name ('input', 'select', or 'textarea').
 * @param {number} index - The index of the variable in the list.
 * @param {string} field - The variable field name ('id', 'type', 'default', etc.).
 * @param {string} value - The initial value.
 * @param {string} [type='text'] - The input type.
 * @returns {HTMLElement}
 */
const createVariableField = (tag, index, field, value, type = 'text') => {
    const element = document.createElement(tag);
    element.className = tag === 'textarea' ? 'form-control form-control-sm' : 'form-control form-control-sm';
    element.dataset.index = index.toString();
    element.dataset.field = field;

    if (tag === 'input') {
        element.type = type;
        element.value = value || '';
    } else if (tag === 'textarea') {
        element.rows = 2;
        element.textContent = value || '';
    } else if (tag === 'select') {
        element.className = 'form-select form-select-sm';
        // Options populated externally in renderVariableRow
    }

    return element;
};

/**
 * Renders a single row for a component variable using robust DOM manipulation.
 * @param {object} variable - The variable object.
 * @param {number} index - The index of the variable in the list.
 * @returns {HTMLDivElement}
 */
const renderVariableRow = (variable, index) => {
    const rowCard = document.createElement('div');
    rowCard.className = 'card mb-3';

    const cardBody = document.createElement('div');
    cardBody.className = 'card-body';

    // Top row with 6 columns for Variable ID, Label, Type, Source, Default, Required
    const topRow = document.createElement('div');
    topRow.className = 'row g-2 align-items-center mb-3';

    const fields = [
        { label: 'Variable ID', field: 'id', tag: 'input', width: 'col-md-2' },
        { label: 'Label (Optional)', field: 'label', tag: 'input', width: 'col-md-2' },
        { label: 'Type', field: 'type', tag: 'select', width: 'col-md-2', options: VARIABLE_TYPES },
        { label: 'Source', field: 'source', tag: 'select', width: 'col-md-2', options: VARIABLE_SOURCES },
        { label: 'Default Value', field: 'default', tag: 'input', width: 'col-md-2' },
        { label: 'Required', field: 'required', tag: 'select', width: 'col-md-2', options: VARIABLE_REQUIRED_OPTIONS }
    ];

    fields.forEach(f => {
        const col = document.createElement('div');
        col.className = f.width;

        const label = document.createElement('label');
        label.className = 'form-label small';
        label.textContent = f.label;
        col.appendChild(label);

        const element = createVariableField(f.tag, index, f.field, variable[f.field]);

        if (f.tag === 'select') {
            const currentVal = variable[f.field];
            const options = Array.isArray(f.options)
                ? (f.field === 'type' ? f.options.map(v => ({ value: v, label: v })) : f.options)
                : [];

            options.forEach(opt => {
                element.appendChild(createOption(opt.value, opt.label, opt.value === currentVal));
            });
        }

        col.appendChild(element);
        topRow.appendChild(col);
    });

    // Description row (full width)
    const descRow = document.createElement('div');
    descRow.className = 'row';
    const descCol = document.createElement('div');
    descCol.className = 'col-12';

    const descLabel = document.createElement('label');
    descLabel.className = 'form-label small';
    descLabel.textContent = 'Description';
    descCol.appendChild(descLabel);

    const descTextarea = createVariableField('textarea', index, 'description', variable.description);
    descCol.appendChild(descTextarea);
    descRow.appendChild(descCol);

    // START OF FIX: Add contextual hint for hash generation
    if (variable.id === 'TRAEFIK_DASHBOARD_USERS') {
        const hashHint = document.createElement('div');
        hashHint.className = 'alert alert-sm alert-warning mt-2 mb-0 small';
        hashHint.innerHTML = '<i class="bi bi-shield-lock-fill"></i> **Security Critical:** Use the **Generate Hash** button at the top right to create a secure password hash. Copy the result into your global `.env` file, and then reference it here using the macro <code>{{ DOTENV.YOUR_KEY }}</code>.';
        descCol.appendChild(hashHint);
    }
    // END OF FIX: Add contextual hint for hash generation

    // Remove button
    const removeButton = document.createElement('button');
    removeButton.className = 'btn btn-sm btn-outline-danger mt-3';
    removeButton.dataset.index = index.toString();
    removeButton.innerHTML = '<i class="bi bi-trash"></i> Remove';

    cardBody.appendChild(topRow);
    cardBody.appendChild(descRow);
    cardBody.appendChild(removeButton);
    rowCard.appendChild(cardBody);

    return rowCard;
};


/**
 * Renders the complete Variables tab pane with all variable rows.
 * It is responsible for *rendering* the initial state and setting up the
 * necessary event listeners for state mutation/dirty tracking.
 *
 * @param {object} params - Parameters for rendering.
 * @param {object[]} params.variables - Array of ComponentVariable objects.
 * @param {function} params.renderAllRowsCallback - A function to re-render all rows (e.g., after adding/deleting).
 * @param {function} params.markTabDirtyCallback - A function to mark the 'variables-pane' as dirty.
 * @param {function} params.onAddVariable - A function to call when the 'Add New Variable' button is clicked.
 */
// START OF FIX: Function signature changed to 'export function' to resolve 'Unused constant' IDE warning.
export function renderVariablesPane({ variables, renderAllRowsCallback, markTabDirtyCallback, onAddVariable }) {
// END OF FIX: Function signature changed to 'export function' to resolve 'Unused constant' IDE warning.
    const container = document.getElementById('variables-pane');
    if (!container) return;
    container.innerHTML = ''; // Clear container

    // 1. Render Hint Alert
    const alertHtml = `
        <div class="alert alert-info small">
            <i class="bi bi-info-circle-fill"></i>
            <strong>Hint:</strong> The <strong>Default Value</strong> field supports special macros.
            Use <code>{{ CONFIG_BASE_PATH }}/your-path</code> for portable data paths, and
            <code>{{ DOTENV.YOUR_GLOBAL_VAR }}</code> to bind the value to the user <strong>.env</strong> file.
            <a href="https://github.com/HenkVanHoek/PiSelfhosting/blob/main/docs/ARCHITECTURE.md#25-the-variable-and-macro-system" target="_blank" class="alert-link">Learn More</a>.
        </div>`;
    container.insertAdjacentHTML('beforeend', alertHtml);

    // 2. Render List Container
    const listContainer = document.createElement('div');
    listContainer.id = 'variables-list';
    listContainer.className = 'mt-3';
    container.appendChild(listContainer);

    // 3. Render Add Button
    const addButton = document.createElement('button');
    addButton.id = 'add-variable-btn';
    addButton.className = 'btn btn-secondary mt-3';
    addButton.innerHTML = '<i class="bi bi-plus-circle"></i> Add New Variable';
    addButton.addEventListener('click', onAddVariable);
    container.appendChild(addButton);

    // Function to render all rows in the list container
    const renderRows = () => {
        listContainer.innerHTML = '';
        if (variables.length === 0) {
            listContainer.innerHTML = '<p class="text-muted">No user variables defined.</p>';
        }
        variables.forEach((variable, index) => {
            listContainer.appendChild(renderVariableRow(variable, index));
        });
    };

    // Set up delegated event listener for changes
    listContainer.addEventListener('input', e => {
        if (e.target.matches('input') || e.target.matches('select') || e.target.matches('textarea')) {
            // START OF FIX: Removed unused destructuring assignment to resolve 'Unused constant index' and 'field' warnings.
            // const { index, field } = e.target.dataset;
            // END OF FIX: Removed unused destructuring assignment to resolve 'Unused constant index' and 'field' warnings.
            // The calling component (editor.v2.js) needs to handle the actual state update
            // and then call renderAllRowsCallback if a re-render is needed.
            // For now, we only mark dirty, as the text/select/checkbox changes
            // are read directly from the DOM later in collectVariablesFromDOM.
            // We'll rely on the main app to handle the data flow.
            markTabDirtyCallback();
        }
    });

    // Set up delegated event listener for remove buttons
    listContainer.addEventListener('click', e => {
        const removeButton = e.target.closest('button');
        if (removeButton && removeButton.dataset.index) {
            // Re-render handled by the main app via the callback after state mutation
            renderAllRowsCallback(parseInt(removeButton.dataset.index, 10));
            markTabDirtyCallback();
        }
    });

    // Initial render of rows
    renderRows();
    return renderRows; // Return the inner render function for easy re-render from editor.v2.js
}

/**
 * Renders the main editor pane with component metadata and sets up event handlers.
 * @param {object} details - Component metadata details.
 * @param {object} componentData - Global component data (for groups datalist).
 * @param {function} markTabDirtyCallback - Function to mark the 'metadata-pane' as dirty.
 * @param {function} handleSaveChanges - Function to call when the save button is clicked.
 * @param {function} handleDeleteComponent - Function to call when the delete button is clicked.
 * @returns {void}
 */
// START OF FIX: Function signature changed to 'export function' to resolve 'Unused constant' IDE warning.
export function renderEditor(details, componentData, markTabDirtyCallback, handleSaveChanges, handleDeleteComponent) {
// END OF FIX: Function signature changed to 'export function' to resolve 'Unused constant' IDE warning.
    const componentId = details.id;
    let dependsOn = Array.isArray(details.depends_on) ? details.depends_on : (details.depends_on ? [details.depends_on] : []);
    const dependsOnStr = dependsOn.join(', ');

    // 1. Update Title
    document.getElementById('editor-title').textContent = details.name || componentId;

    // 2. Render Metadata Pane
    const metadataPane = document.getElementById('metadata-pane');
    if (!metadataPane) return;
    metadataPane.innerHTML = ''; // Clear existing content

    const renderMetadataField = (type, id, label, value, readOnly = false, isCheckbox = false, rows = 1, listId = null) => {
        const div = document.createElement('div');
        div.className = 'mb-3';

        const labelEl = document.createElement('label');
        labelEl.htmlFor = id;
        labelEl.className = 'form-label';
        labelEl.textContent = label;

        let input;
        if (isCheckbox) {
            div.className = 'form-check form-switch mb-2';
            input = document.createElement('input');
            input.className = 'form-check-input';
            input.type = 'checkbox';
            input.role = 'switch';
            input.id = id;
            input.checked = value;
            labelEl.className = 'form-check-label';
            div.appendChild(input);
            div.appendChild(labelEl);
            return div;
        } else if (type === 'textarea') {
            input = document.createElement('textarea');
            input.rows = rows;
            input.textContent = value || '';
        } else {
            input = document.createElement('input');
            input.type = type;
            input.value = value || '';
            if (readOnly) input.readOnly = true;
            if (listId) input.setAttribute('list', listId);
        }

        input.className = 'form-control';
        input.id = id;

        div.appendChild(labelEl);
        div.appendChild(input);
        return div;
    };

    // --- Component ID and Name ---
    metadataPane.appendChild(renderMetadataField('text', 'comp-id', 'Component ID', componentId, true));
    metadataPane.appendChild(renderMetadataField('text', 'comp-name', 'Name', details.name));

    // --- Description ---
    metadataPane.appendChild(renderMetadataField('textarea', 'comp-desc', 'Description', details.description, false, false, 3));

    // --- Group and Depends On (Row layout) ---
    const row = document.createElement('div');
    row.className = 'row';

    // Group Field (with Datalist)
    const colGroup = document.createElement('div');
    colGroup.className = 'col-md-6 mb-3';
    const groupField = renderMetadataField('text', 'comp-group', 'Group', details.group, false, false, 1, 'group-datalist');
    colGroup.appendChild(groupField.firstChild); // Only append the inner div, as renderMetadataField adds the mb-3 wrapper
    colGroup.appendChild(groupField.lastChild);

    // Depends On Field
    const colDeps = document.createElement('div');
    colDeps.className = 'col-md-6 mb-3';
    const depsField = renderMetadataField('text', 'comp-deps', 'Depends On', dependsOnStr);
    colDeps.appendChild(depsField.firstChild);
    colDeps.appendChild(depsField.lastChild);

    row.appendChild(colGroup);
    row.appendChild(colDeps);
    metadataPane.appendChild(row);

    // --- Datalist for Groups ---
    const datalist = document.createElement('datalist');
    datalist.id = 'group-datalist';
    if (componentData && componentData.groups) {
        componentData.groups.forEach(group => {
            const option = document.createElement('option');
            option.value = group.id;
            option.textContent = group.name;
            datalist.appendChild(option);
        });
    }
    // Append the datalist outside the row, where it will be found by the input
    metadataPane.appendChild(datalist);

    // --- Checkboxes ---
    metadataPane.appendChild(renderMetadataField('checkbox', 'comp-has-ui', 'Has Web UI', details.has_ui, false, true));
    metadataPane.appendChild(renderMetadataField('checkbox', 'comp-has-config', 'Has User Configuration', details.has_configuration, false, true));

    // 3. Setup Metadata Event Listener
    metadataPane.addEventListener('input', () => markTabDirtyCallback('metadata-pane'));
    metadataPane.addEventListener('change', () => markTabDirtyCallback('metadata-pane'));

    // 4. Setup Control Buttons
    const saveButton = document.getElementById('save-changes-btn');
    if (saveButton) saveButton.onclick = () => handleSaveChanges(componentId);
    const deleteButton = document.getElementById('delete-component-btn');
    if (deleteButton) deleteButton.onclick = () => handleDeleteComponent(componentId);
}
