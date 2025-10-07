/* global bootstrap, EventSource */
document.addEventListener('DOMContentLoaded', () => {
    /**
     * @typedef {object} PortConflict
     * @property {number} port
     * @property {'DANGEROUS_NATIVE_PROCESS_CONFLICT'|'UNEXPECTED_DOCKER_CONFLICT'|'EXPECTED_REINSTALLATION'} conflict_type
     * @property {string} conflicting_service
     * @property {string} proposed_service
     */

    /**
     * @typedef {object} VolumeConflict
     * @property {string} volume_path
     * @property {'EXISTING_VOLUME_CONFLICT'} conflict_type
     * @property {string} proposed_service
     */

    /**
     * @typedef {object} ResourceWarning
     * @property {'RAM'|'DISK'} type
     * @property {string} message
     */

    /**
     * @typedef {object} SystemAnalysisResponse
     * @property {'success'|'error'} status
     * @property {string[]} [internal_conflicts]
     * @property {{ports: PortConflict[], volumes: VolumeConflict[]}} external_conflicts
     * @property {ResourceWarning[]} resource_warnings
     */

    /**
     * @typedef {object} DeploymentResponse
     * @property {string} task_id
     */

    /**
     * @typedef {object} Host
     * @property {string} ip
     * @property {string} mac
     * @property {string|null} hostname
     */

    /**
     * @typedef {object} ScanData
     * @property {Host[]} hosts
     * @property {string[]} messages
     * @property {boolean} permissions_error
     */

    /**
     * @typedef {object} DiskInfo
     * @property {string} mounted_on
     * @property {string} size
     * @property {string} pcent
     */

    /**
     * @typedef {object} DeviceDetails
     * @property {string} ip
     * @property {string} username
     * @property {string} password
     * @property {string} [hostname]
     * @property {string} [model]
     * @property {string} [serial]
     * @property {string} [ram]
     * @property {DiskInfo[]} disks
     */

    /**
     * @typedef {object} ComponentVariable
     * @property {string} id
     * @property {string} [label]
     * @property {string} description
     * @property {string} type
     * @property {string} [default]
     * @property {string[]} [options]
     * @property {'always'|'clean-install'} [required]
     * @property {'dotenv'} [source]
     */

    /**
     * @typedef {object} Component
     * @property {string} id
     * @property {string} name
     * @property {string} description
     * @property {boolean} [default]
     * @property {string[]} [depends_on]
     * @property {boolean} [post_install_restart_option]
     * @property {ComponentVariable[]} required_variables
     */

    /**
     * @typedef {object} SoftwareResponseData
     * @property {Component[]} available_software
     */

    /**
     * @typedef {object} GroupData
     * @property {Object.<string, string[]>} groups
     */

    /**
     * @typedef {object} ServiceLink
     * @property {string} name
     * @property {string} url
     */

    /**
     * @typedef {object} ReportError
     * @property {string} type
     * @property {string} summary
     * @property {string} details
     * @property {string} component_id
     * @property {string} timestamp
     */

    /**
     * @typedef {object} TaskStatus
     * @property {string} status
     * @property {string[]} logs
     * @property {number} last_update
     * @property {ServiceLink[]} service_links
     * @property {ReportError[]} errors
     */

    /**
     * @typedef {object} ApiError
     * @property {string} message - The error message.
     */

    async function fetchAPI(url, options = {}) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                const message = errorData.error || `Request failed with status ${response.status}`;
                return Promise.reject({ message });
            }
            return response.json();
        } catch (networkError) {
            const error = /** @type {Error} */ (networkError);
            return Promise.reject({ message: error.message || 'Network error, please check the connection.' });
        }
    }

    function setButtonState(button, isLoading, { text = '', loadingText = 'Loading...' } = {}) {
        if (!button) return;
        if (!button.dataset.originalText) {
            button.dataset.originalText = button.innerHTML;
        }
        const originalText = text || button.dataset.originalText;

        button.disabled = isLoading;
        if (isLoading) {
            button.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2"></i>${loadingText}`;
        } else {
            button.innerHTML = originalText;
        }
    }

    function updateWizardFooter(message, type = 'muted') {
        const wizardFooter = document.getElementById('wizard-footer');
        if (wizardFooter) {
            wizardFooter.innerHTML = `<p class="text-${type} small mb-0">${message}</p>`;
        }
    }

    const wizardHeader = document.getElementById('wizard-header');
    const wizardBody = document.getElementById('wizard-body');

    /** @type {Object.<string, DeviceDetails>} */
    let managedDeviceCache = {};
    let selectedComponentsCache = [];
    /** @type {Component[]} */
    let allSoftwareCache = [];
    let finalVariablesCache = {};
    let componentsToCleanCache = [];
    let componentsToRestartCache = [];
    // START OF FIX: Cache for analysis results
    /** @type {SystemAnalysisResponse | {}} */
    let analysisResultsCache = {};
    // END OF FIX

    /** @param {ScanData} scanData */
    const renderStep2_ConfigureDevices = (scanData) => {
        wizardHeader.innerHTML = '<strong>Step 2 of 5: Configure Your Devices</strong>';
        updateWizardFooter('Enter the SSH credentials for the devices you want to manage.');
        const popoverContent = `The scanner looks for two types of devices:
            1. Physical Raspberry Pis by checking for a hardware model file.
            2. PiSelfhosting Virtual Pis by checking for the '/etc/piselfhosting-virtual-pi-server' file inside the guest OS.`;
        wizardBody.innerHTML = `
            <div class="text-start">
                <h2 class="h4 text-center">
                    Device Configuration
                    <i class="fa-solid fa-circle-question text-muted ms-2" style="font-size: 0.8em; cursor: pointer;"
                       data-bs-toggle="popover" data-bs-trigger="hover focus"
                       data-bs-title="How Detection Works"
                       data-bs-content="${popoverContent}"></i>
                </h2>
                <p class="text-muted text-center small mb-4">
                    Found ${scanData.hosts.length} potential Pi network interfaces.
                    Provide credentials for each device to get more details.
                </p>
                <div class="card card-body bg-light mb-4">
                    <h3 class="h6">Common Actions</h3>
                    <p class="small text-muted">Use these fields to apply credentials to all devices, or to clear all selections.</p>
                    <div class="row g-2">
                        <div class="col-sm-4"><input type="text" class="form-control form-control-sm" id="master-username" placeholder="Username"></div>
                        <div class="col-sm-4"><input type="password" class="form-control form-control-sm" id="master-password" placeholder="Password"></div>
                        <div class="col-sm-2 d-grid"><button class="btn btn-secondary btn-sm" id="apply-to-all-btn">Apply</button></div>
                        <div class="col-sm-2 d-grid"><button class="btn btn-outline-secondary btn-sm" id="deselect-all-btn">Clear All</button></div>
                    </div>
                </div>
                <div id="device-cards-container" class="row row-cols-1 row-cols-md-2 row-cols-lg-3 row-cols-xl-4 g-4"></div>
                <div class="d-grid gap-2 col-8 mx-auto my-4" id="step2-action-area">
                    <button id="get-details-btn" class="btn btn-primary btn-lg">
                        <i class="fa-solid fa-plug-circle-check me-2"></i>
                        Connect & Get Details
                    </button>
                </div>
            </div>
        `;
        const container = document.getElementById('device-cards-container');
        scanData.hosts.forEach((host, index) => {
            const cardWrapper = document.createElement('div');
            cardWrapper.className = 'col';
            cardWrapper.innerHTML = `
                <div class="card h-100 device-card" data-ip="${host.ip}" data-hostname="${host.hostname || 'Unknown Host'}">
                    <div class="card-body d-flex flex-column">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <h5 class="card-title mb-0 me-3">
                                <i class="fa-solid fa-server me-2"></i>${host.hostname || 'Unknown Host'}
                            </h5>
                            <div class="form-check form-switch text-nowrap">
                                <input class="form-check-input" type="checkbox" role="switch" id="manageDeviceSwitch-${index}">
                                <label class="form-check-label" for="manageDeviceSwitch-${index}">Manage</label>
                            </div>
                        </div>
                        <p class="card-text text-muted small">IP: ${host.ip} | MAC: ${host.mac}</p>
                        <div class="row g-2">
                            <!-- FIX: Add disabled attribute to fields as default is unmanaged (OFF) -->
                            <div class="col-sm-6"><input type="text" class="form-control form-control-sm device-username" placeholder="Username" disabled></div>
                            <div class="col-sm-6"><input type="password" class="form-control form-control-sm device-password" placeholder="Password" disabled></div>
                        </div>
                        <div class="hardware-details mt-auto pt-3" style="font-size: 0.8rem; display: none;"></div>
                    </div>
                    <div class="card-footer text-body-secondary small">
                        Status: <span class="status-text">Pending credentials...</span>
                    </div>
                </div>
            `;
            container.appendChild(cardWrapper);
        });

        // FIX: Add logic to toggle disabled state on switch change
        document.querySelectorAll('.device-card').forEach(card => {
            const manageSwitch = card.querySelector('[type="checkbox"]');
            const usernameInput = card.querySelector('.device-username');
            const passwordInput = card.querySelector('.device-password');

            if (manageSwitch && usernameInput && passwordInput) {
                // Function to toggle disabled state
                const toggleDisabled = () => {
                    const isDisabled = !(/** @type {HTMLInputElement} */ (manageSwitch)).checked;
                    usernameInput.disabled = isDisabled;
                    passwordInput.disabled = isDisabled;
                };

                // Add event listener to the switch
                manageSwitch.addEventListener('change', toggleDisabled);

                // Add event listeners to the input fields for the 'Autoforce ON' behavior
                [usernameInput, passwordInput].forEach(input => {
                    input.addEventListener('input', () => {
                        // If the switch is OFF and the user starts typing, force it ON
                        if (!(/** @type {HTMLInputElement} */ (manageSwitch)).checked && input.value.length > 0) {
                            (/** @type {HTMLInputElement} */ (manageSwitch)).checked = true;
                            toggleDisabled(); // Re-run to update disabled state immediately
                        }
                    });
                });

                // Initial state update (redundant here, but good practice)
                toggleDisabled();
            }
        });

        document.getElementById('apply-to-all-btn').addEventListener('click', () => {
            const masterUsername = (/** @type {HTMLInputElement} */ (document.getElementById('master-username'))).value;
            const masterPassword = (/** @type {HTMLInputElement} */ (document.getElementById('master-password'))).value;
            document.querySelectorAll('.device-username').forEach(input => (/** @type {HTMLInputElement} */ (input)).value = masterUsername);
            document.querySelectorAll('.device-password').forEach(input => (/** @type {HTMLInputElement} */ (input)).value = masterPassword);
        });
        document.getElementById('deselect-all-btn').addEventListener('click', () => {
            document.querySelectorAll('.device-card .form-check-input').forEach(s => (/** @type {HTMLInputElement} */ (s)).checked = false);
        });
        const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
        Array.from(popoverTriggerList).forEach(el => new bootstrap.Popover(el, {}));
        document.getElementById('get-details-btn').addEventListener('click', handleGetDeviceDetails);
    };

    const handleGetDeviceDetails = async () => {
        managedDeviceCache = {};
        const actionArea = document.getElementById('step2-action-area');
        const getDetailsBtn = document.getElementById('get-details-btn');
        setButtonState(getDetailsBtn, true, { loadingText: 'Connecting...' });

        const promises = [];
        document.querySelectorAll('.device-card').forEach(card => {
            if (!(/** @type {HTMLInputElement} */ (card.querySelector('[type="checkbox"]'))).checked) return;

            const ip = (/** @type {HTMLElement} */ (card)).dataset.ip;
            const hostname = (/** @type {HTMLElement} */ (card)).dataset.hostname;
            const username = (/** @type {HTMLInputElement} */ (card.querySelector('.device-username'))).value;
            const password = (/** @type {HTMLInputElement} */ (card.querySelector('.device-password'))).value;
            const statusEl = card.querySelector('.status-text');
            const detailsEl = (/** @type {HTMLElement} */ (card.querySelector('.hardware-details')));

            detailsEl.style.display = 'none';
            detailsEl.innerHTML = '';
            statusEl.className = 'status-text text-primary';
            statusEl.textContent = 'Connecting...';

            const promise = fetchAPI('/get-device-details', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ip, username, password })
            })
            .then(data => {
                /** @type {DeviceDetails} */
                const details = data.details;
                statusEl.className = 'status-text text-success fw-bold';
                statusEl.textContent = `Success! (Model: ${details.model || 'Unknown Model'})`;
                managedDeviceCache[ip] = { ...details, ip, username, password, hostname };
                const diskInfo = details.disks.find(d => d.mounted_on === '/');
                detailsEl.innerHTML = `
                    <hr class="my-2">
                    <span><i class="fa-solid fa-microchip me-1"></i> Serial: ${details.serial || 'N/A'}</span><br>
                    <span><i class="fa-solid fa-memory me-1"></i> RAM: ${details.ram || 'N/A'}</span><br>
                    <span><i class="fa-solid fa-hard-drive me-1"></i> Disk: ${diskInfo ? `${diskInfo.size} (${diskInfo.pcent} used)` : 'N/A'}</span>
                `;
                detailsEl.style.display = 'block';
            })
            .catch(error => {
                console.error(`Error for IP ${ip}:`, error);
                statusEl.className = 'status-text text-danger';
                statusEl.textContent = `Failed: ${error.message || 'Unknown error'}`;
                delete managedDeviceCache[ip];
            });
            promises.push(promise);
        });

        await Promise.allSettled(promises);

        if (Object.keys(managedDeviceCache).length > 0) {
            actionArea.innerHTML = `<button id="proceed-to-step3-btn" class="btn btn-success btn-lg"><i class="fa-solid fa-arrow-right-to-bracket me-2"></i> Proceed to Software Selection</button>`;
            updateWizardFooter(`Found ${Object.keys(managedDeviceCache).length} manageable device(s). Ready to proceed.`, 'success');
            document.getElementById('proceed-to-step3-btn').addEventListener('click', renderStep3_SelectSoftware);
        } else {
            setButtonState(getDetailsBtn, false, { text: '<i class="fa-solid fa-plug-circle-check me-2"></i>Try Again' });
            updateWizardFooter('No devices could be successfully contacted. Check credentials and click "Try Again".', 'danger');
        }
    };

    /** @param {Component} component
     * @param groupName
     * @param type
     */
    const createComponentInput = (component, groupName, type) => {
        const inputName = type === 'radio' ? `group-${groupName}` : `component-${component.id}`;
        return `
            <div class="form-check mb-2">
                <input class="form-check-input" type="${type}" name="${inputName}" value="${component.id}" id="comp-${component.id}" ${component.default ? 'checked' : ''}>
                <label class="form-check-label" for="comp-${component.id}"><strong>${component.name}</strong></label>
            </div>
            <p class="card-text small text-muted ms-4 mb-3">${component.description}</p>
        `;
    };

    const renderStep3_SelectSoftware = async () => {
        wizardHeader.innerHTML = '<strong>Step 3 of 5: Select Software</strong>';
        wizardBody.innerHTML = `<div class="text-center"><i class="fa-solid fa-spinner fa-spin fa-2x text-muted"></i><p class="mt-2">Loading available software...</p></div>`;
        updateWizardFooter('Choose software to install. Selections in a category are mutually exclusive.');

        try {
            /** @type {[SoftwareResponseData, GroupData]} */
            const [softwareData, groupsData] = await Promise.all([
                fetchAPI('/get-available-software', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ devices: Object.values(managedDeviceCache) })
                }),
                fetchAPI('/get-software-groups')
            ]);

            allSoftwareCache = softwareData.available_software;
            const groups = groupsData.groups;
            const allGroupedComponents = new Set(Object.values(groups).flat());

            let tabNavHTML = '<ul class="nav nav-tabs" id="softwareTabs" role="tablist">';
            let tabContentHTML = '<div class="tab-content" id="softwareTabsContent">';
            let active = 'active';

            Object.keys(groups).forEach((groupName) => {
                const tabId = `tab-${groupName.replace(/\s+/g, '-')}`;
                tabNavHTML += `<li class="nav-item" role="presentation"><button class="nav-link ${active}" data-bs-toggle="tab" data-bs-target="#${tabId}" type="button">${groupName}</button></li>`;
                tabContentHTML += `<div class="tab-pane fade show ${active} p-3" id="${tabId}" role="tabpanel">`;
                groups[groupName].forEach(compId => {
                    const component = allSoftwareCache.find(c => c.id === compId);
                    if (component) tabContentHTML += createComponentInput(component, groupName, 'radio');
                });
                tabContentHTML += `</div>`;
                active = '';
            });

            tabNavHTML += `<li class="nav-item" role="presentation"><button class="nav-link ${active}" data-bs-toggle="tab" data-bs-target="#tab-standalone" type="button">Standalone</button></li>`;
            tabContentHTML += `<div class="tab-pane fade show ${active} p-3" id="tab-standalone" role="tabpanel">`;
            allSoftwareCache.forEach(component => {
                if (!allGroupedComponents.has(component.id)) {
                    tabContentHTML += createComponentInput(component, 'standalone', 'checkbox');
                }
            });

            tabNavHTML += '</ul>';
            tabContentHTML += '</div>';

            wizardBody.innerHTML = `
                <div class="text-start">
                    <h2 class="h4 text-center">Select Software</h2>
                    <p class="text-muted text-center small mb-4">Select the software you wish to install on your ${Object.keys(managedDeviceCache).length} selected device(s).</p>
                    ${tabNavHTML}
                    ${tabContentHTML}
                    <div class="d-grid gap-2 col-8 mx-auto my-4">
                        <button id="proceed-to-step4-btn" class="btn btn-primary btn-lg"><i class="fa-solid fa-sliders me-2"></i> Configure Services</button>
                    </div>
                </div>
            `;
            document.getElementById('proceed-to-step4-btn').addEventListener('click', renderStep4_ConfigureServices);
        } catch (error) {
            console.error('Error fetching software list:', error);
            wizardBody.innerHTML = `<p class="text-center text-danger">An error occurred while loading the software list: ${error.message}</p>`;
        }
    };

    /** @param {ComponentVariable} variable */
    const createVariableInput = (variable) => {
        const inputId = `var-${variable.id}`;
        let inputHTML;

        if (variable.source === 'dotenv') {
            const placeholder = '******** (Managed in .env file)';
            inputHTML = `<input type="text" class="form-control form-control-sm" id="${inputId}" name="${variable.id}" value="" placeholder="${placeholder}" disabled>`;
        } else if (variable.type === 'select' && variable.options) {
            const optionsHTML = variable.options.map(opt => `<option value="${opt}" ${opt === variable.default ? 'selected' : ''}>${opt}</option>`).join('');
            inputHTML = `<select class="form-select form-select-sm" id="${inputId}" name="${variable.id}">${optionsHTML}</select>`;
        } else {
            const inputType = variable.type === 'password' ? 'password' : 'text';
            inputHTML = `<input type="${inputType}" class="form-control form-control-sm" id="${inputId}" name="${variable.id}" value="${variable.default || ''}">`;
        }

        return `
            <div class="mb-3">
                <label for="${inputId}" class="form-label"><strong>${variable.label || variable.id}</strong></label>
                ${inputHTML}
                <div class="form-text small">${variable.description}</div>
            </div>
        `;
    };

    const validateConfiguration = () => {
        let isValid = true;
        let errorMessage = '';
        document.querySelectorAll('#variables-container .tab-pane').forEach(tab => {
            const compId = tab.id.replace('v-pills-', '');
            const isCleanInstall = (/** @type {HTMLInputElement} */ (document.getElementById(`clean-install-checkbox-${compId}`)))?.checked;
            const componentData = allSoftwareCache.find(c => c.id === compId);

            componentData?.required_variables?.forEach(variable => {
                const input = /** @type {HTMLInputElement|HTMLSelectElement} */ (tab.querySelector(`[name="${variable.id}"]`));
                if (!input) return;

                const isRequired = variable.required === 'always' || (variable.required === 'clean-install' && isCleanInstall);
                if (isRequired && !input.value) {
                    if (isValid) {
                        isValid = false;
                        errorMessage = `The '${variable.label || variable.id}' field is required for ${componentData.name}.`;
                    }
                    input.classList.add('is-invalid');
                } else {
                    input.classList.remove('is-invalid');
                }
            });
        });

        const reviewBtn = /** @type {HTMLButtonElement} */ (document.getElementById('review-selection-btn'));
        if (reviewBtn) reviewBtn.disabled = !isValid;

        const errorDiv = document.getElementById('config-error-display');
        if (errorDiv) {
            errorDiv.textContent = isValid ? '' : errorMessage;
            errorDiv.style.display = isValid ? 'none' : 'block';
        }

        return isValid;
    };

    const addRealTimeValidation = () => {
        document.querySelectorAll('.clean-install-checkbox, #variables-container input, #variables-container select').forEach(el => {
            const eventListener = () => {
                validateConfiguration();
            };
            el.addEventListener('input', eventListener);
            el.addEventListener('change', eventListener);
        });
        validateConfiguration();
    };

    const renderStep4_ConfigureServices = async () => {
        selectedComponentsCache = Array.from(document.querySelectorAll('#softwareTabsContent .form-check-input:checked')).map(input => (/** @type {HTMLInputElement} */ (input)).value);
        wizardHeader.innerHTML = '<strong>Step 4 of 5: Configure Services</strong>';
        updateWizardFooter('Provide the required values for your selected software.');

        if (selectedComponentsCache.length === 0) {
            wizardBody.innerHTML = `<p class="text-center text-muted">No software was selected. Please go back and select at least one component.</p>`;
            return;
        }

        wizardBody.innerHTML = `<div class="text-center"><i class="fa-solid fa-spinner fa-spin fa-2x text-muted"></i><p class="mt-2">Loading configuration options...</p></div>`;

        try {
            const data = await fetchAPI('/get-required-variables', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_components: selectedComponentsCache })
            });

            const components = data.components;
            const componentsRequiringUi = selectedComponentsCache.filter(compId => {
                const fullComp = allSoftwareCache.find(c => c.id === compId);
                return (Object.keys(components).includes(compId)) || (fullComp && fullComp.post_install_restart_option);
            });

            if (componentsRequiringUi.length === 0) {
                 wizardBody.innerHTML = `
                    <div class="text-start">
                        <h2 class="h4 text-center">Configure Services</h2>
                        <p class="text-center text-muted">The selected software requires no additional configuration.</p>
                        <div class="d-grid gap-2 col-8 mx-auto my-4">
                           <button id="review-selection-btn" class="btn btn-primary btn-lg"><i class="fa-solid fa-clipboard-check me-2"></i> Review and Confirm</button>
                        </div>
                    </div>
                `;
                document.getElementById('review-selection-btn').addEventListener('click', handleReviewSelection);
                return;
            }

            let navPillsHTML = '<div class="nav flex-column nav-pills me-3" role="tablist" aria-orientation="vertical">';
            let tabContentHTML = '<div class="tab-content">';
            let isFirstItem = true;

            selectedComponentsCache.forEach(compId => {
                const componentWithVars = components[compId];
                const fullComponentData = allSoftwareCache.find(c => c.id === compId);
                if (!fullComponentData || (!componentWithVars && !fullComponentData.post_install_restart_option)) return;

                const tabId = `v-pills-${compId}`;
                const activeClass = isFirstItem ? 'active' : '';
                navPillsHTML += `<button class="nav-link text-start ${activeClass}" data-bs-toggle="pill" data-bs-target="#${tabId}" type="button">${fullComponentData.name}</button>`;
                tabContentHTML += `<div class="tab-pane fade show ${activeClass}" id="${tabId}" role="tabpanel">`;

                if (componentWithVars?.variables?.length > 0) {
                    componentWithVars.variables.forEach(v => { tabContentHTML += createVariableInput(v); });
                } else {
                    tabContentHTML += '<p class="text-center text-muted pt-4">This component requires no variable configuration.</p>';
                }

                tabContentHTML += `<hr>
                    <div class="form-check mt-3">
                        <input class="form-check-input clean-install-checkbox" type="checkbox" id="clean-install-checkbox-${compId}" data-comp-id="${compId}">
                        <label class="form-check-label" for="clean-install-checkbox-${compId}"><strong>Perform a clean reinstallation</strong></label>
                        <div class="form-text small">This will permanently delete all existing data and settings for this service before deploying.</div>
                    </div>`;

                if (fullComponentData.post_install_restart_option) {
                    tabContentHTML += `
                        <div class="form-check mt-3">
                            <input class="form-check-input restart-checkbox" type="checkbox" id="restart-checkbox-${compId}" data-comp-id="${compId}">
                            <label class="form-check-label" for="restart-checkbox-${compId}"><strong>Restart container after installation</strong></label>
                            <div class="form-text small">Recommended for services that require a restart to initialize properly.</div>
                        </div>`;
                }
                tabContentHTML += '</div>';
                isFirstItem = false;
            });

            navPillsHTML += '</div>';
            tabContentHTML += '</div>';

            wizardBody.innerHTML = `
                <div class="text-start">
                    <h2 class="h4 text-center">Configure Services</h2>
                    <p class="text-muted text-center small mb-4">Provide the required settings for your selected software.</p>
                    <div class="row">
                        <div class="col-md-3">${navPillsHTML}</div>
                        <div class="col-md-9"><div id="variables-container">${tabContentHTML}</div></div>
                    </div>
                    <div class="d-grid gap-2 col-8 mx-auto my-4">
                        <div id="config-error-display" class="alert alert-danger" style="display: none;" role="alert"></div>
                        <button id="review-selection-btn" class="btn btn-primary btn-lg"><i class="fa-solid fa-clipboard-check me-2"></i> Review and Confirm</button>
                    </div>
                </div>
            `;
            addRealTimeValidation();
            document.getElementById('review-selection-btn').addEventListener('click', handleReviewSelection);
        } catch (error) {
            console.error('Error fetching variables:', error);
            wizardBody.innerHTML = `<p class="text-center text-danger">An error occurred while loading configuration options: ${error.message}</p>`;
        }
    };

    /** @param {SystemAnalysisResponse} analysisData */
    const displayAnalysisResults = (analysisData) => {
        let warningsHTML = '';
        let expectedChangesHTML = '';
        let blockingConflictsHTML = '';
        let isBlocked = false;

        analysisData.resource_warnings?.forEach(w => {
            warningsHTML += `<li class="list-group-item"><i class="fa-solid fa-triangle-exclamation text-warning me-2"></i><strong>${w.type} Warning:</strong> ${w.message}</li>`;
        });

        analysisData.external_conflicts?.ports?.forEach(p => {
            if (p.conflict_type === 'EXPECTED_REINSTALLATION') {
                expectedChangesHTML += `<li class="list-group-item"><i class="fa-solid fa-arrows-rotate text-info me-2"></i><strong>Port ${p.port} Re-use:</strong> The existing service <strong>${p.conflicting_service}</strong> will be stopped and replaced by <strong>${p.proposed_service}</strong>.</li>`;
            } else {
                isBlocked = true;
                const icon = p.conflict_type === 'DANGEROUS_NATIVE_PROCESS_CONFLICT' ? 'fa-shield-halved' : 'fa-network-wired';
                blockingConflictsHTML += `<li class="list-group-item"><i class="fa-solid ${icon} text-danger me-2"></i><strong>Port ${p.port} Conflict:</strong> This port is already in use by a critical service: <strong>${p.conflicting_service}</strong>. You must change the port for <strong>${p.proposed_service}</strong> to continue.</li>`;
            }
        });

        analysisData.external_conflicts?.volumes?.forEach(v => {
            warningsHTML += `<li class="list-group-item"><i class="fa-solid fa-folder-open text-warning me-2"></i><strong>Shared Volume:</strong> The path <strong>${v.volume_path}</strong> is already in use and will be shared with <strong>${v.proposed_service}</strong>. This is usually safe but be aware.</li>`;
        });

        const modalBodyHTML = `
            ${isBlocked ? `<div class="alert alert-danger" role="alert"><h4 class="alert-heading">Action Required</h4><p>One or more blocking conflicts were detected. Please review the items below and adjust your configuration before proceeding.</p></div>` : ''}
            ${blockingConflictsHTML ? `<h5><i class="fa-solid fa-ban me-2"></i>Blocking Conflicts</h5><ul class="list-group mb-4">${blockingConflictsHTML}</ul>` : ''}
            ${expectedChangesHTML ? `<h5><i class="fa-solid fa-info-circle me-2"></i>Expected Changes</h5><ul class="list-group mb-4">${expectedChangesHTML}</ul>` : ''}
            ${warningsHTML ? `<h5><i class="fa-solid fa-triangle-exclamation me-2"></i>Warnings</h5><ul class="list-group mb-2">${warningsHTML}</ul>` : ''}
            ${!blockingConflictsHTML && !expectedChangesHTML && !warningsHTML ? '<p class="text-center text-success"><i class="fa-solid fa-check-circle me-2"></i>No conflicts or warnings found. Your configuration looks good to go!</p>' : ''}
        `;

        document.getElementById('analysis-modal')?.remove();
        const modalHTML = `
            <div class="modal fade" id="analysis-modal" tabindex="-1" aria-labelledby="analysisModalLabel" aria-hidden="true">
              <div class="modal-dialog modal-lg modal-dialog-centered">
                <div class="modal-content">
                  <div class="modal-header">
                    <h5 class="modal-title" id="analysisModalLabel">Pre-flight Check Summary</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                  </div>
                  <div class="modal-body">${modalBodyHTML}</div>
                  <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Go Back &amp; Edit</button>
                    <button type="button" class="btn btn-primary" id="modal-proceed-btn" ${isBlocked ? 'disabled' : ''}>${isBlocked ? 'Cannot Proceed' : 'Proceed to Confirmation'}</button>
                  </div>
                </div>
              </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        const analysisModal = new bootstrap.Modal(document.getElementById('analysis-modal'));
        document.getElementById('modal-proceed-btn').addEventListener('click', () => {
            analysisModal.hide();
            renderStep5_Confirmation();
        });
        analysisModal.show();
    };

    const handleReviewSelection = async () => {
        if (!validateConfiguration()) return;

        const reviewBtn = document.getElementById('review-selection-btn');
        const errorDiv = document.getElementById('config-error-display');
        setButtonState(reviewBtn, true, { loadingText: 'Analyzing...' });

        finalVariablesCache = {};
        document.querySelectorAll('#variables-container [name]:not(:disabled)').forEach(input => {
            const el = /** @type {HTMLInputElement|HTMLSelectElement} */ (input);
            finalVariablesCache[el.name] = el.value;
        });

        componentsToCleanCache = Array.from(document.querySelectorAll('.clean-install-checkbox:checked')).map(cb => (/** @type {HTMLElement} */ (cb)).dataset.compId);
        componentsToRestartCache = Array.from(document.querySelectorAll('.restart-checkbox:checked')).map(cb => (/** @type {HTMLElement} */ (cb)).dataset.compId);

        const componentsPayload = selectedComponentsCache.map(compId => {
            const componentData = allSoftwareCache.find(c => c.id === compId);
            const component = { name: componentData?.name || compId, ports: [], volumes: [] };
            componentData?.required_variables?.forEach(variable => {
                const userValue = finalVariablesCache[variable.id];
                if (userValue) {
                    if (variable.id.toUpperCase().endsWith('_PORT')) {
                        component.ports.push(`${userValue}:${userValue}/tcp`);
                    } else if (variable.id.toUpperCase().endsWith('_VOLUME_PATH')) {
                        component.volumes.push(userValue);
                    }
                }
            });
            return component;
        });

        try {
            const analysisData = await fetchAPI('/api/v1/system/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    devices: Object.values(managedDeviceCache),
                    components: componentsPayload,
                    is_reinstallation: componentsToCleanCache.length > 0
                })
            });

            if (analysisData.status === 'error') {
                const message = analysisData.internal_conflicts?.join(', ') || 'An internal validation error occurred.';
                if (errorDiv) {
                    errorDiv.textContent = message;
                    errorDiv.style.display = 'block';
                }
            } else {
                // START OF FIX: Cache the analysis results
                analysisResultsCache = analysisData;
                // END OF FIX
                displayAnalysisResults(analysisData);
            }
        } catch (error) {
            console.error('Analysis failed:', error);
            if (errorDiv) {
                errorDiv.textContent = error.message || 'An unknown server error occurred.';
                errorDiv.style.display = 'block';
            }
        } finally {
            setButtonState(reviewBtn, false);
        }
    };

    const renderStep5_Confirmation = () => {
        wizardHeader.innerHTML = '<strong>Step 5 of 5: Confirmation</strong>';
        updateWizardFooter('Please review your selections before generating files and deploying.');
        const devicesHTML = Object.values(managedDeviceCache).map(device => `<li><strong>${device.hostname || 'Unknown Host'}</strong> (${device.ip})</li>`).join('');
        const softwareHTML = selectedComponentsCache.map(compId => {
            const component = allSoftwareCache.find(c => c.id === compId);
            return `<li><strong>${component?.name || 'Unknown'}</strong>: ${component?.description || 'No description.'}</li>`;
        }).join('');

        wizardBody.innerHTML = `
            <div class="text-start">
                <h2 class="h4 text-center">Confirmation Summary</h2>
                <div class="card my-4"><div class="card-header">Target Devices</div><div class="card-body"><ul class="list-unstyled mb-0">${devicesHTML}</ul></div></div>
                <div class="card mb-4"><div class="card-header">Selected Software</div><div class="card-body"><ul class="mb-0">${softwareHTML}</ul></div></div>
                <div class="d-grid gap-2 col-8 mx-auto my-4">
                    <button id="final-generate-btn" class="btn btn-success btn-lg"><i class="fa-solid fa-file-invoice me-2"></i>Generate Configuration Files</button>
                </div>
            </div>`;
        document.getElementById('final-generate-btn').addEventListener('click', handleInstallation);
    };

    const handleInstallation = async () => {
        const installBtn = document.getElementById('final-generate-btn');
        setButtonState(installBtn, true, { loadingText: 'Generating files...' });

        try {
            const result = await fetchAPI('/start-installation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    selected_components: selectedComponentsCache,
                    devices: Object.values(managedDeviceCache),
                    env_vars: finalVariablesCache,
                    components_to_clean: componentsToCleanCache,
                })
            });

            wizardHeader.innerHTML = '<strong>Setup Complete</strong>';
            updateWizardFooter('Ready for deployment.');
            wizardBody.innerHTML = `
                <div class="text-center">
                    <i class="fa-solid fa-circle-check fa-3x text-success mb-3"></i>
                    <h2 class="h4">Files Generated Successfully!</h2>
                    <p class="text-muted">Your configuration files are ready.</p>
                    <div class="card card-body bg-light text-start my-3"><pre><code id="output-path-display">${result.output_path}</code></pre></div>
                    <div id="final-actions-container">
                         <div class="d-grid gap-2 d-md-flex justify-content-md-center mt-4" id="deployment-actions">
                            <button id="deploy-button" class="btn btn-primary"><i class="fa-solid fa-rocket me-2"></i>Deploy to Pi(s)</button>
                            <button onclick="location.reload();" class="btn btn-secondary">Start Over</button>
                        </div>
                    </div>
                    <div id="log-viewer-container" class="mt-4 text-start" style="display: none;">
                        <h3 class="h5 text-center">Deployment Progress</h3>
                        <div class="card"><div class="card-body bg-dark text-white rounded" style="font-family: monospace; font-size: 0.9em; max-height: 400px; overflow-y: auto;">
                            <pre id="log-output" class="mb-0" style="white-space: pre-wrap;"></pre>
                        </div></div>
                    </div>
                </div>`;
            document.getElementById('deploy-button').addEventListener('click', () => {
                const outputPath = document.getElementById('output-path-display').textContent;
                handleDeployment(outputPath);
            });
        } catch (error) {
            console.error('Installation failed:', error);
            wizardHeader.innerHTML = '<strong>Generation Failed</strong>';
            updateWizardFooter('The process could not be completed.', 'danger');
            const errorDetails = error.details || [error.message || 'An unknown error occurred.'];
            const GITHUB_REPO_URL = "https://github.com/HenkVanHoek/PiSelfhosting";
            const issueBody = encodeURIComponent(`**Error Details:**\n\n\`\`\`\n${errorDetails.join('\n')}\n\`\`\`\n\n**Context:**\n- Selected Components: ${selectedComponentsCache.join(', ')}`);
            const githubIssueURL = `${GITHUB_REPO_URL}/issues/new?title=${encodeURIComponent("Configurator UI Error Report")}&body=${issueBody}`;
            wizardBody.innerHTML = `
                <div class="text-center">
                    <i class="fa-solid fa-circle-xmark fa-3x text-danger mb-3"></i>
                    <h2 class="h4">File Generation Failed</h2>
                    <p class="text-muted">An error occurred during the file generation process.</p>
                    <div class="accordion my-3" id="errorAccordion">
                      <div class="accordion-item">
                        <h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapseOne"><strong>Click to view detailed error report</strong></button></h2>
                        <div id="collapseOne" class="accordion-collapse collapse" data-bs-parent="#errorAccordion"><div class="accordion-body text-start">
                            <p class="small text-muted">Please copy the full text below when reporting an issue.</p>
                            <textarea class="form-control" rows="8" readonly>**Error Details:**\n\`\`\`\n${errorDetails.join('\n')}\n\`\`\`</textarea>
                        </div></div>
                      </div>
                    </div>
                    <p class="text-muted small mt-4">This may be a known issue. Please check the Q&A section.</p>
                    <div class="d-grid gap-2 col-8 mx-auto mt-2">
                        <a href="${GITHUB_REPO_URL}/discussions" target="_blank" class="btn btn-info"><i class="fa-solid fa-comments me-2"></i>Check Q&A / Discussions</a>
                        <a href="${githubIssueURL}" target="_blank" class="btn btn-outline-secondary"><i class="fa-brands fa-github me-2"></i>Report Issue on GitHub</a>
                        <button onclick="location.reload()" class="btn btn-primary mt-2">Start Over</button>
                    </div>
                </div>`;
        }
    };

    /** @param {string} outputPath */
    const handleDeployment = async (outputPath) => {
        const deployButton = document.getElementById('deploy-button');
        const logContainer = document.getElementById('log-viewer-container');
        const logOutput = document.getElementById('log-output');
        let taskId;

        setButtonState(deployButton, true, { loadingText: 'Deploying...' });
        logContainer.style.display = 'block';
        logOutput.innerHTML = '';

        try {
            // START OF FIX: Construct the full component data payload
            const selectedComponentsData = selectedComponentsCache
                .map(id => allSoftwareCache.find(c => c.id === id))
                .filter(Boolean); // Filter out any potential nulls
            // END OF FIX

            /** @type {DeploymentResponse} */
            const data = await fetchAPI('/deploy-configuration', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    output_path: outputPath,
                    devices: Object.values(managedDeviceCache),
                    components_to_clean: componentsToCleanCache,
                    components_to_restart: componentsToRestartCache,
                    // START OF FIX: Pass the required data to the backend
                    analysis_results: analysisResultsCache,
                    selected_components_data: selectedComponentsData,
                    global_vars: finalVariablesCache
                    // END OF FIX
                }),
            });

            taskId = data.task_id;
            const eventSource = new EventSource(`/stream-deployment/${taskId}`);
            let hasErrors = false;

            const watchdogTimer = setTimeout(() => {
                eventSource.close();
                logOutput.innerHTML += '\n<span class="text-danger fw-bold">[ERROR] Connection to server timed out.</span>\n';
                updateWizardFooter('Connection timed out. Please check the backend console.', 'danger');
                setButtonState(deployButton, false, { text: '<i class="fa-solid fa-triangle-exclamation me-2"></i>Deployment Failed - Retry?' });
            }, 30000);

            eventSource.onmessage = event => {
                clearTimeout(watchdogTimer);
                const line = event.data;
                let className = 'text-light';
                if (line.includes('SUCCESS:')) className = 'text-success';
                if (line.includes('ERROR:') || line.includes('FATAL:')) {
                    className = 'text-danger';
                    hasErrors = true;
                }
                if (line.includes('WARN:')) className = 'text-warning';
                if (line.includes('---')) className = 'text-info fw-bold';
                const span = document.createElement('span');
                span.className = className;
                span.textContent = line + '\n';
                logOutput.appendChild(span);
                logOutput.parentElement.scrollTop = logOutput.parentElement.scrollHeight;
            };

            eventSource.onerror = () => {
                clearTimeout(watchdogTimer);
                eventSource.close();
                if (hasErrors) {
                    // START OF FIX: Re-assign the button's click handler to show errors
                    setButtonState(deployButton, false, { text: '<i class="fa-solid fa-triangle-exclamation me-2"></i>Show Error Report' });
                    updateWizardFooter('Deployment completed, but some steps failed.', 'warning');
                    deployButton.onclick = () => showErrorSummary(taskId);
                    // END OF FIX
                } else {
                    setButtonState(deployButton, false, { text: '<i class="fa-solid fa-circle-check me-2"></i>Deployment Finished' });
                    updateWizardFooter('Deployment process completed successfully.', 'success');
                    const finalActions = document.getElementById('final-actions-container');
                    if (finalActions) {
                        finalActions.innerHTML = `
                            <div class="d-grid gap-2 col-8 mx-auto my-4">
                                 <button id="show-summary-btn" class="btn btn-info btn-lg"><i class="fa-solid fa-list-check me-2"></i>Access Your Services</button>
                            </div>`;
                        document.getElementById('show-summary-btn').addEventListener('click', () => showServicesSummary(taskId));
                    }
                }
            };
        } catch (error) {
            console.error('Failed to start deployment:', error);
            logOutput.innerHTML += `<span class="text-danger fw-bold">ERROR: Failed to initiate deployment. ${error.message}\n</span>`;
            setButtonState(deployButton, false, { text: '<i class="fa-solid fa-triangle-exclamation me-2"></i>Deployment Failed - Retry?' });
            updateWizardFooter('Could not start deployment process.', 'danger');
        }
    };

    // START OF FIX: New function to display a modal with the structured error report
    /** @param {string} taskId */
    const showErrorSummary = async (taskId) => {
        const errorBtn = document.getElementById('deploy-button');
        setButtonState(errorBtn, true, { loadingText: 'Fetching Report...' });
        try {
            /** @type {TaskStatus} */
            const taskData = await fetchAPI(`/task-status/${taskId}`);
            let errorsHTML = '';
            if (taskData.errors && taskData.errors.length > 0) {
                errorsHTML = taskData.errors.map(err => `
                    <div class="list-group-item">
                        <div class="d-flex w-100 justify-content-between">
                            <h6 class="mb-1">${err.summary}</h6>
                            <small class="text-muted">${err.timestamp}</small>
                        </div>
                        <p class="mb-1 small"><strong>Type:</strong> ${err.type}</p>
                        <p class="mb-1 small"><strong>Details:</strong> ${err.details}</p>
                        <small class="text-muted">Component: ${err.component_id}</small>
                    </div>
                `).join('');
            } else {
                errorsHTML = '<p class="text-center">No detailed error information was found for this task.</p>';
            }

            document.getElementById('error-report-modal')?.remove();
            const modalHTML = `
                <div class="modal fade" id="error-report-modal" tabindex="-1" aria-labelledby="errorReportModalLabel" aria-hidden="true">
                  <div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
                    <div class="modal-content">
                      <div class="modal-header">
                        <h5 class="modal-title" id="errorReportModalLabel">Deployment Error Report</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                      </div>
                      <div class="modal-body">
                        <p>The following errors occurred during the deployment process:</p>
                        <div class="list-group">${errorsHTML}</div>
                      </div>
                      <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                      </div>
                    </div>
                  </div>
                </div>`;
            document.body.insertAdjacentHTML('beforeend', modalHTML);
            const errorModal = new bootstrap.Modal(document.getElementById('error-report-modal'));
            errorModal.show();
        } catch (error) {
            console.error('Failed to fetch error summary:', error);
            updateWizardFooter('Could not retrieve the error report.', 'danger');
        } finally {
            setButtonState(errorBtn, false, { text: '<i class="fa-solid fa-triangle-exclamation me-2"></i>Show Error Report' });
        }
    };
    // END OF FIX

    /** @param {string} taskId */
    const showServicesSummary = async (taskId) => {
        const summaryBtn = document.getElementById('show-summary-btn');
        setButtonState(summaryBtn, true, { loadingText: 'Loading...' });
        try {
            /** @type {TaskStatus} */
            const finalData = await fetchAPI(`/task-status/${taskId}`);
            if (finalData.service_links?.length > 0) {
                const linksHTML = finalData.service_links.map(link => `<li><a href="${link.url}" target="_blank">${link.name}</a>: <code>${link.url}</code></li>`).join('');
                const summaryBox = `<div id="service-links-summary" class="card mt-4 text-start"><div class="card-header fw-bold">Access Your Services</div><div class="card-body"><ul class="list-unstyled mb-0">${linksHTML}</ul></div></div>`;
                document.getElementById('service-links-summary')?.remove();
                document.getElementById('log-viewer-container').insertAdjacentHTML('beforebegin', summaryBox);
                setButtonState(summaryBtn, false, { text: '<i class="fa-solid fa-check me-2"></i>Summary Loaded' });
            } else {
                setButtonState(summaryBtn, false, { text: 'No Web Interfaces Found' });
            }
        } catch (error) {
            console.error("Failed to show summary:", error);
            setButtonState(summaryBtn, false, { text: 'Error Loading Summary' });
        }
    };

    const setupStep1 = () => {
        const scanBtn = document.getElementById('begin-scan-btn');
        const manualInput = /** @type {HTMLInputElement} */ (document.getElementById('manualSubnetInput'));
        document.getElementById('autoDetectRadio').addEventListener('change', (e) => { manualInput.disabled = (/** @type {HTMLInputElement} */ (e.target)).checked; });
        document.getElementById('manualScanRadio').addEventListener('change', (e) => {
            if ((/** @type {HTMLInputElement} */ (e.target)).checked) {
                manualInput.disabled = false;
                manualInput.focus();
            }
        });

        const performScan = async () => {
            setButtonState(scanBtn, true, { loadingText: 'Scanning...' });
            updateWizardFooter('Scanning network for Raspberry Pi devices...', 'primary');
            const subnetToScan = (/** @type {HTMLInputElement} */ (document.getElementById('manualScanRadio'))).checked ? manualInput.value : null;

            try {
                /** @type {ScanData} */
                const data = await fetchAPI('/scan-pis', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ subnet: subnetToScan })
                });
                if (data.permissions_error) {
                    const troubleshootingUrl = 'https://github.com/HenkVanHoek/PiSelfhosting/blob/main/docs/TROUBLESHOOTING.md#network-scan-issues';
                    updateWizardFooter(`<strong>Warning:</strong> The scanner may not have required permissions. Please check our <a href='${troubleshootingUrl}' target='_blank'>troubleshooting guide</a>.`, 'warning');
                } else {
                    renderStep2_ConfigureDevices(data);
                }
            } catch (error) {
                console.error('An error occurred during the scan:', error);
                updateWizardFooter(`<i class="fa-solid fa-xmark me-2"></i>An error occurred: ${error.message}`, 'danger');
            } finally {
                setButtonState(scanBtn, false);
                scanBtn.innerHTML = '<i class="fa-solid fa-search me-2"></i> Begin Scan';
            }
        };
        scanBtn.addEventListener('click', performScan);
    };

    setupStep1();
});
