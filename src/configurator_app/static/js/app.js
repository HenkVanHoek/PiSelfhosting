document.addEventListener('DOMContentLoaded', () => {
    const wizardHeader = document.getElementById('wizard-header');
    const wizardBody = document.getElementById('wizard-body');
    const wizardFooter = document.getElementById('wizard-footer');

    let managedDeviceCache = {};
    let selectedComponentsCache = [];

    const renderStep2_ConfigureDevices = (scanData) => {
        wizardHeader.innerHTML = '<strong>Step 2 of 5: Configure Your Devices</strong>';
        wizardFooter.innerHTML = '<p class="text-muted small mb-0">Enter the SSH credentials for the devices you want to manage.</p>';

        wizardBody.innerHTML = `
            <div class="text-start">
                <h2 class="h4 text-center">
                    Device Configuration
                    <i class="fa-solid fa-circle-question text-muted ms-2" style="font-size: 0.8em; cursor: pointer;"
                       data-bs-toggle="popover" data-bs-trigger="hover focus"
                       data-bs-title="How Detection Works"
                       data-bs-content="The scanner looks for two types of devices: 1. Physical Raspberry Pis by checking for a hardware model file. 2. PiSelfhosting Virtual Pis by checking for the '/etc/piselfhosting-virtual-pi-server' file inside the guest OS."></i>
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
            const cardHTML = `
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
                            <div class="col-sm-6"><input type="text" class="form-control form-control-sm device-username" placeholder="Username"></div>
                            <div class="col-sm-6"><input type="password" class="form-control form-control-sm device-password" placeholder="Password"></div>
                        </div>
                        <div class="hardware-details mt-auto pt-3" style="font-size: 0.8rem; display: none;"></div>
                    </div>
                    <div class="card-footer text-body-secondary small">
                        Status: <span class="status-text">Pending credentials...</span>
                    </div>
                </div>
            `;
            cardWrapper.innerHTML = cardHTML;
            container.appendChild(cardWrapper);
        });

        document.getElementById('apply-to-all-btn').addEventListener('click', () => {
            document.querySelectorAll('.device-username').forEach(input => input.value = document.getElementById('master-username').value);
            document.querySelectorAll('.device-password').forEach(input => input.value = document.getElementById('master-password').value);
        });
        document.getElementById('deselect-all-btn').addEventListener('click', () => {
            document.querySelectorAll('.device-card .form-check-input').forEach(s => s.checked = false);
        });

        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(el => new bootstrap.Popover(el));

        document.getElementById('get-details-btn').addEventListener('click', handleGetDeviceDetails);
    };

    const handleGetDeviceDetails = async () => {
        managedDeviceCache = {};
        const actionArea = document.getElementById('step2-action-area');
        const getDetailsBtn = document.getElementById('get-details-btn');
        getDetailsBtn.disabled = true;
        getDetailsBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2"></i>Connecting...`;

        const promises = [];
        document.querySelectorAll('.device-card').forEach(card => {
            if (!card.querySelector('[type="checkbox"]').checked) return;

            const ip = card.dataset.ip;
            const hostname = card.dataset.hostname;
            const username = card.querySelector('.device-username').value;
            const password = card.querySelector('.device-password').value;
            const statusEl = card.querySelector('.status-text');
            const detailsEl = card.querySelector('.hardware-details');

            detailsEl.style.display = 'none';
            detailsEl.innerHTML = '';
            statusEl.className = 'status-text text-primary';
            statusEl.textContent = 'Connecting...';

            const promise = fetch('/get-device-details', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ip, username, password })
            })
            .then(response => response.ok ? response.json() : Promise.reject(response.json()))
            .then(data => {
                statusEl.className = 'status-text text-success fw-bold';
                statusEl.textContent = `Success! (Model: ${data.details.model || 'Unknown Model'})`;

                managedDeviceCache[ip] = { ...data.details, ip, username, password, hostname };

                const details = data.details;
                const diskInfo = details.disks.find(d => d.mounted_on === '/');
                detailsEl.innerHTML = `
                    <hr class="my-2">
                    <span><i class="fa-solid fa-microchip me-1"></i> Serial: ${details.serial || 'N/A'}</span><br>
                    <span><i class="fa-solid fa-memory me-1"></i> RAM: ${details.ram || 'N/A'}</span><br>
                    <span><i class="fa-solid fa-hard-drive me-1"></i> Disk: ${diskInfo ? `${diskInfo.size} (${diskInfo.pcent} used)` : 'N/A'}</span>
                `;
                detailsEl.style.display = 'block';
            })
            .catch(async errorPromise => {
                const error = await errorPromise;
                console.error(`Error for IP ${ip}:`, error);
                statusEl.className = 'status-text text-danger';
                statusEl.textContent = `Failed: ${error.error || 'Unknown error'}`;
                delete managedDeviceCache[ip];
            });
            promises.push(promise);
        });

        await Promise.allSettled(promises);

        if (Object.keys(managedDeviceCache).length > 0) {
            actionArea.innerHTML = `<button id="proceed-to-step3-btn" class="btn btn-success btn-lg"><i class="fa-solid fa-arrow-right-to-bracket me-2"></i> Proceed to Software Selection</button>`;
            wizardFooter.innerHTML = `<p class="text-success small mb-0">Found ${Object.keys(managedDeviceCache).length} manageable device(s). Ready to proceed.</p>`;
            document.getElementById('proceed-to-step3-btn').addEventListener('click', renderStep3_SelectSoftware);
        } else {
            getDetailsBtn.disabled = false;
            getDetailsBtn.innerHTML = `<i class="fa-solid fa-plug-circle-check me-2"></i>Try Again`;
            wizardFooter.innerHTML = `<p class="text-danger small mb-0">No devices could be successfully contacted. Check credentials and click 'Try Again'.</p>`;
        }
    };

    const renderStep3_SelectSoftware = async () => {
        wizardHeader.innerHTML = '<strong>Step 3 of 5: Select Software</strong>';
        wizardBody.innerHTML = `<div class="text-center"><i class="fa-solid fa-spinner fa-spin fa-2x text-muted"></i><p class="mt-2">Loading available software...</p></div>`;
        wizardFooter.innerHTML = '<p class="text-muted small mb-0">Choose software to install. Selections in a category are mutually exclusive.</p>';

        try {
            const [softwareResponse, groupsResponse] = await Promise.all([
                fetch('/get-available-software', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ devices: Object.values(managedDeviceCache) })
                }),
                fetch('/get-software-groups')
            ]);

            if (!softwareResponse.ok) throw await softwareResponse.json();
            if (!groupsResponse.ok) throw await groupsResponse.json();

            const softwareData = await softwareResponse.json();
            const groupsData = await groupsResponse.json();
            const softwareList = softwareData.available_software;
            const groups = groupsData.groups;
            const allGroupedComponents = new Set(Object.values(groups).flat());

            let tabNavHTML = '<ul class="nav nav-tabs" id="softwareTabs" role="tablist">';
            let tabContentHTML = '<div class="tab-content" id="softwareTabsContent">';
            let active = 'active';

            Object.keys(groups).forEach((groupName) => {
                const tabId = `tab-${groupName.replace(/\s+/g, '-')}`;
                tabNavHTML += `<li class="nav-item" role="presentation"><button class="nav-link ${active}" id="${tabId}-tab" data-bs-toggle="tab" data-bs-target="#${tabId}" type="button" role="tab">${groupName}</button></li>`;
                tabContentHTML += `<div class="tab-pane fade show ${active} p-3" id="${tabId}" role="tabpanel">`;
                groups[groupName].forEach(compId => {
                    const component = softwareList.find(c => c.id === compId);
                    if (component) tabContentHTML += createComponentInput(component, groupName, 'radio');
                });
                tabContentHTML += `</div>`;
                active = '';
            });

            tabNavHTML += `<li class="nav-item" role="presentation"><button class="nav-link ${active}" id="tab-standalone-tab" data-bs-toggle="tab" data-bs-target="#tab-standalone" type="button" role="tab">Standalone</button></li>`;
            tabContentHTML += `<div class="tab-pane fade show ${active} p-3" id="tab-standalone" role="tabpanel">`;
            softwareList.forEach(component => {
                if (!allGroupedComponents.has(component.id)) {
                    tabContentHTML += createComponentInput(component, 'standalone', 'checkbox');
                }
            });
            tabContentHTML += `</div>`;
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
            wizardBody.innerHTML = `<p class="text-center text-danger">An error occurred while loading the software list.</p>`;
        }
    };

    const createComponentInput = (component, groupName, type) => {
        const inputName = type === 'radio' ? `group-${groupName}` : `component-${component.id}`;
        const isChecked = component.default ? 'checked' : '';
        return `
            <div class="form-check mb-2">
                <input class="form-check-input" type="${type}" name="${inputName}" value="${component.id}" id="comp-${component.id}" ${isChecked}>
                <label class="form-check-label" for="comp-${component.id}"><strong>${component.name}</strong></label>
            </div>
            <p class="card-text small text-muted ms-4 mb-3">${component.description}</p>
        `;
    };

    const renderStep4_ConfigureServices = async () => {
        const allInputs = document.querySelectorAll('#softwareTabsContent .form-check-input');
        selectedComponentsCache = Array.from(allInputs)
                                      .filter(input => input.checked)
                                      .map(input => input.value);

        wizardHeader.innerHTML = '<strong>Step 4 of 5: Configure Services</strong>';
        wizardFooter.innerHTML = '<p class="text-muted small mb-0">Provide the required values for your selected software.</p>';

        if (selectedComponentsCache.length === 0) {
            wizardBody.innerHTML = `<p class="text-center text-muted">No software was selected. Please go back and select at least one component.</p>`;
            return;
        }

        wizardBody.innerHTML = `<div class="text-center"><i class="fa-solid fa-spinner fa-spin fa-2x text-muted"></i><p class="mt-2">Loading configuration options...</p></div>`;

        try {
            const response = await fetch('/get-required-variables', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_components: selectedComponentsCache })
            });

            if (!response.ok) throw await response.json();

            const data = await response.json();
            const components = data.components;
            const componentIds = Object.keys(components);

            if (componentIds.length === 0) {
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

            let navPillsHTML = '<div class="nav flex-column nav-pills me-3" id="v-pills-tab" role="tablist" aria-orientation="vertical">';
            let tabContentHTML = '<div class="tab-content" id="v-pills-tabContent">';
            let isFirstItem = true;

            componentIds.forEach(compId => {
                const component = components[compId];
                const tabId = `v-pills-${compId}`;
                const activeClass = isFirstItem ? 'active' : '';
                const showClass = isFirstItem ? 'show active' : '';

                navPillsHTML += `<button class="nav-link text-start ${activeClass}" id="${tabId}-tab" data-bs-toggle="pill" data-bs-target="#${tabId}" type="button" role="tab">${component.name}</button>`;
                tabContentHTML += `<div class="tab-pane fade ${showClass}" id="${tabId}" role="tabpanel">`;
                if (component.variables && component.variables.length > 0) {
                    component.variables.forEach(v => { tabContentHTML += createVariableInput(v); });
                } else {
                    tabContentHTML += '<p class="text-center text-muted pt-4">This component requires no configuration.</p>';
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
                        <div class="col-md-9"><div id="variables-form-container">${tabContentHTML}</div></div>
                    </div>
                    <div class="d-grid gap-2 col-8 mx-auto my-4">
                        <button id="review-selection-btn" class="btn btn-primary btn-lg"><i class="fa-solid fa-clipboard-check me-2"></i> Review and Confirm</button>
                    </div>
                </div>
            `;

            document.getElementById('review-selection-btn').addEventListener('click', handleReviewSelection);

        } catch (error) {
            console.error('Error fetching variables:', error);
            wizardBody.innerHTML = `<p class="text-center text-danger">An error occurred while loading configuration options.</p>`;
        }
    };

    const createVariableInput = (variable) => {
        let inputHTML = '';
        const inputId = `var-${variable.id}`;
        const type = variable.type || 'string';

        if (type === 'select' && variable.options) {
            const optionsHTML = variable.options.map(opt => `<option value="${opt}" ${opt === variable.default ? 'selected' : ''}>${opt}</option>`).join('');
            inputHTML = `<select class="form-select form-select-sm" id="${inputId}" name="${variable.id}">${optionsHTML}</select>`;
        } else {
            const inputType = type === 'password' ? 'password' : 'text';
            inputHTML = `<input type="${inputType}" class="form-control form-control-sm" id="${inputId}" name="${variable.id}" value="${variable.default || ''}">`;
        }

        return `
            <div class="mb-3">
                <label for="${inputId}" class="form-label"><strong>${variable.name}</strong></label>
                ${inputHTML}
                <div class="form-text small">${variable.description}</div>
            </div>
        `;
    };

    const handleReviewSelection = async () => {
        const reviewBtn = document.getElementById('review-selection-btn');
        reviewBtn.disabled = true;
        reviewBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2"></i>Validating...`;

        const final_vars = {};
        document.querySelectorAll('#variables-form-container [name]').forEach(input => {
            final_vars[input.name] = input.value;
        });

        try {
            const portResponse = await fetch('/validate-ports', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ final_vars: final_vars })
            });
            if (!portResponse.ok) throw await portResponse.json();

            const templateResponse = await fetch('/validate-selection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_components: selectedComponentsCache })
            });
            if (!templateResponse.ok) throw await templateResponse.json();

            await renderStep5_Confirmation();

        } catch (error) {
            console.error('Validation failed:', error);
            // --- THE IMPROVED ERROR REPORTING ---
            const errorMessage = error.error || (error.message || 'An unknown server error occurred. Please check the backend console for details.');
            wizardFooter.innerHTML = `<p class="text-danger small mb-0">${errorMessage}</p>`;
            reviewBtn.disabled = false;
            reviewBtn.innerHTML = `<i class="fa-solid fa-clipboard-check me-2"></i> Review and Confirm`;
        }
    };

    const renderStep5_Confirmation = async () => {
        wizardHeader.innerHTML = '<strong>Step 5 of 5: Confirmation</strong>';
        wizardFooter.innerHTML = '<p class="text-muted small mb-0">Please review your selections before generating files and deploying.</p>';
        wizardBody.innerHTML = `<div class="text-center"><i class="fa-solid fa-spinner fa-spin fa-2x text-muted"></i><p class="mt-2">Loading summary...</p></div>`;

        try {
            const response = await fetch('/get-available-software', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ devices: Object.values(managedDeviceCache) })
            });
            if (!response.ok) throw await response.json();
            const softwareData = await response.json();
            const allSoftware = softwareData.available_software;

            let devicesHTML = Object.values(managedDeviceCache).map(device =>
                `<li><strong>${device.hostname || 'Unknown Host'}</strong> (${device.ip})</li>`
            ).join('');

            let softwareHTML = selectedComponentsCache.map(compId => {
                const component = allSoftware.find(c => c.id === compId);
                return `<li><strong>${component.name || compId}</strong>: ${component.description || 'No description.'}</li>`;
            }).join('');

            wizardBody.innerHTML = `
                <div class="text-start">
                    <h2 class="h4 text-center">Confirmation Summary</h2>
                    <div class="card my-4">
                        <div class="card-header">Target Devices</div>
                        <div class="card-body"><ul class="list-unstyled mb-0">${devicesHTML}</ul></div>
                    </div>
                    <div class="card mb-4">
                        <div class="card-header">Selected Software</div>
                        <div class="card-body"><ul class="mb-0">${softwareHTML}</ul></div>
                    </div>
                    <div class="d-grid gap-2 col-8 mx-auto my-4">
                        <button id="final-generate-btn" class="btn btn-success btn-lg">
                            <i class="fa-solid fa-file-invoice me-2"></i>
                            Generate Configuration Files
                        </button>
                    </div>
                </div>
            `;

            document.getElementById('final-generate-btn').addEventListener('click', handleInstallation);

        } catch (error) {
            wizardBody.innerHTML = `<p class="text-danger text-center">Could not load summary. Please try again.</p>`;
        }
    };

    const handleInstallation = async () => {
        const installBtn = document.getElementById('final-generate-btn');
        installBtn.disabled = true;
        installBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2"></i>Generating files...`;

        const envVars = {};
        document.querySelectorAll('#variables-form-container [name]').forEach(input => {
            envVars[input.name] = input.value;
        });

        try {
            const response = await fetch('/start-installation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    selected_components: selectedComponentsCache,
                    devices: Object.values(managedDeviceCache),
                    env_vars: envVars
                })
            });

            if (!response.ok) throw await response.json();
            const result = await response.json();

            wizardHeader.innerHTML = '<strong>Setup Complete</strong>';
            wizardBody.innerHTML = `
                <div class="text-center">
                    <i class="fa-solid fa-circle-check fa-3x text-success mb-3"></i>
                    <h2 class="h4">Files Generated Successfully!</h2>
                    <p class="text-muted">Your configuration files are ready.</p>
                    <div class="card card-body bg-light text-start my-3">
                        <pre><code id="output-path-display">${result.output_path}</code></pre>
                    </div>
                    <div id="final-actions-container">
                         <div class="d-grid gap-2 d-md-flex justify-content-md-center mt-4" id="deployment-actions">
                            <button id="deploy-button" class="btn btn-primary"><i class="fa-solid fa-rocket me-2"></i>Deploy to Pi(s)</button>
                            <button onclick="location.reload();" class="btn btn-secondary">Start Over</button>
                        </div>
                    </div>
                    <div id="log-viewer-container" class="mt-4 text-start" style="display: none;">
                        <h3 class="h5 text-center">Deployment Progress</h3>
                        <div class="card">
                            <div class="card-body bg-dark text-white rounded" style="font-family: 'Courier New', Courier, monospace; font-size: 0.9em; max-height: 400px; overflow-y: auto;">
                                <pre id="log-output" class="mb-0" style="white-space: pre-wrap;"></pre>
                            </div>
                        </div>
                    </div>
                </div>`;
            wizardFooter.innerHTML = '<p class="text-muted small mb-0">Ready for deployment.</p>';

            document.getElementById('deploy-button').addEventListener('click', function() {
                const outputPath = document.getElementById('output-path-display').textContent;
                const deployButton = this;
                const logContainer = document.getElementById('log-viewer-container');
                const logOutput = document.getElementById('log-output');
                let hasErrors = false;
                let eventSource;
                let watchdogTimer;
                let taskId;

                const startWatchdog = () => {
                    watchdogTimer = setTimeout(() => {
                        console.error("Watchdog timeout: No message received for 30 seconds.");
                        if (eventSource) eventSource.close();
                        const lineElement = document.createElement('span');
                        lineElement.className = 'text-danger fw-bold';
                        lineElement.textContent = '\n[ERROR] Connection to server timed out. The process may have stalled.\n';
                        logOutput.appendChild(lineElement);
                        logOutput.parentElement.scrollTop = logOutput.parentElement.scrollHeight;

                        deployButton.disabled = false;
                        deployButton.innerHTML = `<i class="fa-solid fa-triangle-exclamation me-2"></i>Deployment Failed - Retry?`;
                        wizardFooter.innerHTML = `<p class="text-danger small mb-0">Connection timed out. Please check the backend console.</p>`;
                    }, 30000);
                };

                const resetWatchdog = () => {
                    clearTimeout(watchdogTimer);
                    startWatchdog();
                };

                deployButton.disabled = true;
                deployButton.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2"></i>Deploying...`;
                logContainer.style.display = 'block';
                logOutput.innerHTML = '';

                fetch('/deploy-configuration', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        output_path: outputPath,
                        devices: Object.values(managedDeviceCache)
                    }),
                })
                .then(response => {
                    if (!response.ok) { return response.json().then(err => Promise.reject(err)); }
                    return response.json();
                })
                .then(data => {
                    taskId = data.task_id;
                    eventSource = new EventSource(`/stream-deployment/${taskId}`);

                    eventSource.onopen = function() { resetWatchdog(); };
                    eventSource.onmessage = function(event) {
                        resetWatchdog();
                        const line = event.data;
                        let className = 'text-light';
                        if (line.includes('SUCCESS:')) className = 'text-success';
                        if (line.includes('ERROR:')) { className = 'text-danger'; hasErrors = true; }
                        if (line.includes('WARN:')) className = 'text-warning';
                        if (line.includes('---')) className = 'text-info fw-bold';

                        const lineElement = document.createElement('span');
                        lineElement.className = className;
                        lineElement.textContent = line + '\n';
                        logOutput.appendChild(lineElement);
                        logOutput.parentElement.scrollTop = logOutput.parentElement.scrollHeight;
                    };

                    eventSource.onerror = function() {
                        clearTimeout(watchdogTimer);
                        eventSource.close();

                        if (hasErrors) {
                            deployButton.innerHTML = `<i class="fa-solid fa-triangle-exclamation me-2"></i>Deployment Finished with Errors`;
                            wizardFooter.innerHTML = `<p class="text-warning small mb-0">Deployment completed, but some steps failed.</p>`;
                        } else {
                            deployButton.innerHTML = `<i class="fa-solid fa-circle-check me-2"></i>Deployment Finished`;
                            wizardFooter.innerHTML = `<p class="text-success small mb-0">Deployment process completed successfully.</p>`;

                            const finalActions = document.getElementById('final-actions-container');
                            finalActions.innerHTML = `
                                <div class="d-grid gap-2 col-8 mx-auto my-4">
                                     <button id="show-summary-btn" class="btn btn-info btn-lg">
                                        <i class="fa-solid fa-list-check me-2"></i>
                                        Access Your Services
                                    </button>
                                </div>`;

                            document.getElementById('show-summary-btn').addEventListener('click', () => {
                                showServicesSummary(taskId);
                            });
                        }
                    };
                })
                .catch(error => {
                    console.error('Failed to start deployment:', error);
                    const errorLine = document.createElement('span');
                    errorLine.className = 'text-danger fw-bold';
                    errorLine.textContent = `ERROR: Failed to initiate deployment. ${error.error || 'Server is unreachable.'}\n`;
                    logOutput.appendChild(errorLine);
                    deployButton.disabled = false;
                    deployButton.innerHTML = `<i class="fa-solid fa-triangle-exclamation me-2"></i>Deployment Failed - Retry?`;
                    wizardFooter.innerHTML = `<p class="text-danger small mb-0">Could not start deployment process.</p>`;
                });
            });

        } catch (error) {
            console.error('Installation failed:', error);
            wizardHeader.innerHTML = '<strong>Generation Failed</strong>';
            const errorDetails = error.details || ['An unknown error occurred.'];
            const errorReportForCopy = `**Error Details:**\n\`\`\`\n${errorDetails.join('\n')}\n\`\`\`\n\n**Context:**\n- Selected Components: ${selectedComponentsCache.join(', ')}\n- Browser: ${navigator.userAgent}\n`;
            const GITHUB_REPO_URL = "https://github.com/HenkVanHoek/PiSelfhosting";
            const QA_URL = `${GITHUB_REPO_URL}/discussions`;
            const issueTitle = encodeURIComponent("Configurator UI Error Report");
            const issueBody = encodeURIComponent(`**Error Details:**\n\n[Please C/P the full error report from the previous page here.]\n\n**Context:**\n- Selected Components: ${selectedComponentsCache.join(', ')}\n- Browser: ${navigator.userAgent}\n`);
            const githubIssueURL = `${GITHUB_REPO_URL}/issues/new?title=${issueTitle}&body=${issueBody}`;

            wizardBody.innerHTML = `
                <div class="text-center">
                    <i class="fa-solid fa-circle-xmark fa-3x text-danger mb-3"></i>
                    <h2 class="h4">File Generation Failed</h2>
                    <p class="text-muted">An error occurred during the file generation process.</p>
                    <div class="accordion my-3" id="errorAccordion">
                      <div class="accordion-item">
                        <h2 class="accordion-header" id="headingOne">
                          <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapseOne" aria-expanded="false" aria-controls="collapseOne">
                            <strong>Click to view detailed error report</strong>
                          </button>
                        </h2>
                        <div id="collapseOne" class="accordion-collapse collapse" aria-labelledby="headingOne" data-bs-parent="#errorAccordion">
                          <div class="accordion-body text-start">
                            <p class="small text-muted">Please copy the full text below when reporting an issue.</p>
                            <textarea class="form-control" rows="8" readonly>${errorReportForCopy}</textarea>
                          </div>
                        </div>
                      </div>
                    </div>
                    <p class="text-muted small mt-4">This may be a known issue. Please check the Q&A section.</p>
                    <div class="d-grid gap-2 col-8 mx-auto mt-2">
                        <a href="${QA_URL}" target="_blank" class="btn btn-info"><i class="fa-solid fa-comments me-2"></i>Check Q&A / Discussions</a>
                        <a href="${githubIssueURL}" target="_blank" class="btn btn-outline-secondary"><i class="fa-brands fa-github me-2"></i>Report Issue on GitHub</a>
                        <button onclick="location.reload()" class="btn btn-primary mt-2">Start Over</button>
                    </div>
                </div>
            `;
            wizardFooter.innerHTML = `<p class="text-danger small mb-0">The process could not be completed.</p>`;
        }
    };

    const showServicesSummary = async (taskId) => {
        const summaryBtn = document.getElementById('show-summary-btn');
        summaryBtn.disabled = true;
        summaryBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2"></i>Loading...`;

        try {
            const response = await fetch(`/task-status/${taskId}`);
            if (!response.ok) throw new Error("Failed to fetch task status.");
            const finalData = await response.json();

            if (finalData.service_links && finalData.service_links.length > 0) {
                let linksHTML = finalData.service_links.map(link =>
                    `<li><a href="${link.url}" target="_blank">${link.name}</a>: <code>${link.url}</code></li>`
                ).join('');

                const summaryBox = `
                    <div id="service-links-summary" class="card mt-4 text-start">
                        <div class="card-header fw-bold">Access Your Services</div>
                        <div class="card-body">
                            <ul class="list-unstyled mb-0">${linksHTML}</ul>
                        </div>
                    </div>
                `;
                const existingSummary = document.getElementById('service-links-summary');
                if (existingSummary) existingSummary.remove();

                document.getElementById('log-viewer-container').insertAdjacentHTML('beforebegin', summaryBox);
                summaryBtn.innerHTML = `<i class="fa-solid fa-check me-2"></i>Summary Loaded`;
            } else {
                summaryBtn.innerHTML = `No Web Interfaces Found`;
            }
        } catch (error) {
            console.error("Failed to show summary:", error);
            summaryBtn.innerHTML = `Error Loading Summary`;
        }
    };

    const setupStep1 = () => {
        const scanBtn = document.getElementById('begin-scan-btn');
        const autoRadio = document.getElementById('autoDetectRadio');
        const manualRadio = document.getElementById('manualScanRadio');
        const manualInput = document.getElementById('manualSubnetInput');

        autoRadio.addEventListener('change', () => { manualInput.disabled = autoRadio.checked; });
        manualRadio.addEventListener('change', () => {
            if (manualRadio.checked) {
                manualInput.disabled = false;
                manualInput.focus();
            }
        });

        const performScan = async () => {
            scanBtn.disabled = true;
            wizardFooter.innerHTML = `<p class="text-primary small mb-0"><i class="fa-solid fa-spinner fa-spin me-2"></i>Scanning network...</p>`;
            let subnetToScan = manualRadio.checked ? manualInput.value : null;
            try {
                const response = await fetch('/scan-pis', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ subnet: subnetToScan })
                });
                if (!response.ok) throw await response.json();
                const data = await response.json();
                if (data.permissions_error) {
                    wizardFooter.innerHTML = `<div class="text-start text-warning small p-2">...</div>`;
                } else {
                    renderStep2_ConfigureDevices(data);
                }
            } catch (error) {
                console.error('An error occurred during the scan:', error);
                wizardFooter.innerHTML = `<p class="text-danger small mb-0"><i class="fa-solid fa-xmark me-2"></i>An error occurred.</p>`;
            }
        };

        scanBtn.addEventListener('click', performScan);
    };

    setupStep1();
});