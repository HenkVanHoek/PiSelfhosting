// noinspection DuplicatedCode
/* global bootstrap, EventSource */
// Enclose in an IIFE to avoid global scope pollution and bypass DOMContentLoaded race conditions
(function() {
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
     * @property {string} [package_id]
     * @property {boolean} [default]
     * @property {string[]} [depends_on]
     * @property {boolean} [post_install_restart_option]
     * @property {ComponentVariable[]} required_variables
     * @property {boolean} has_traefik_support
     * @property {string} [ui_port_variable]
     * @property {string} [protocol]
     */

    /**
     * @typedef {object} PackageData
     * @property {string} name
     * @property {string} description
     */

    /**
     * @typedef {object} SoftwareResponseData
     * @property {Component[]} available_software
     * @property {Object.<string, PackageData>} [available_packages]
     */

    /**
     * @typedef {object} GroupDetails
     * @property {boolean} is_exclusive
     * @property {string[]} components
     */

    /**
     * @typedef {object} GroupData
     * @property {Object.<string, GroupDetails|string[]>} groups
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

    // Simple HTML escape helper to prevent DOM-XSS
    function escapeHTML(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#x27;');
    }

    async function fetchAPI(url, options = {}) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                const message = errorData.details || errorData.error || `Request failed with status ${response.status}`;
                return Promise.reject({message, details: errorData.details});
            }
            return response.json();
        } catch (networkError) {
            const error = /** @type {Error} */ (networkError);
            return Promise.reject({message: error.message || 'Network error, please check the connection.'});
        }
    }

    function setButtonState(button, isLoading, {text = '', loadingText = 'Loading...'} = {}) {
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

    // Mitigation for DOM-XSS: updateWizardFooter is now completely programmatical
    function updateWizardFooter(message, type = 'muted') {
        const wizardFooter = document.getElementById('wizard-footer');
        if (!wizardFooter) return;

        wizardFooter.textContent = '';
        const p = document.createElement('p');
        p.className = `text-${type} small mb-0`;

        if (message.includes('Warning:') && message.includes('troubleshooting guide')) {
            const strong = document.createElement('strong');
            strong.textContent = 'Warning:';
            p.appendChild(strong);
            p.appendChild(document.createTextNode(' The scanner may not have required permissions. Please check our '));
            const a = document.createElement('a');
            a.href = 'https://github.com/HenkVanHoek/PiSelfhosting/blob/main/docs/TROUBLESHOOTING.md#network-scan-issues';
            a.target = '_blank';
            a.className = 'alert-link';
            a.textContent = 'troubleshooting guide';
            p.appendChild(a);
            p.appendChild(document.createTextNode('.'));
        } else if (message.includes('An error occurred:')) {
            const icon = document.createElement('i');
            icon.className = 'fa-solid fa-xmark me-2';
            p.appendChild(icon);
            p.appendChild(document.createTextNode(message.replace('<i class="fa-solid fa-xmark me-2"></i>', '')));
        } else {
            p.textContent = message;
        }
        wizardFooter.appendChild(p);
    }

    const wizardHeader = document.getElementById('wizard-header');
    const wizardBody = document.getElementById('wizard-body');

    /** @type {Object.<string, DeviceDetails>} */
    let managedDeviceCache = {};
    /** @type {string[]} */
    let selectedComponentsCache = [];
    /** @type {Component[]} */
    let allSoftwareCache = [];
    /** @type {Object.<string, any>} */
    let finalVariablesCache = {};
    /** @type {string[]} */
    let componentsToCleanCache = [];
    /** @type {string[]} */
    let componentsToRestartCache = [];
    /** @type {SystemAnalysisResponse | {}} */
    let analysisResultsCache = {};

    // Caches to preserve step states for Back button transitions
    /** @type {ScanData | null} */
    let lastScanData = null;
    let lastSubnetInput = '';

    // Bulletproof: Hide progress bar row and wizard-header directly via CSS selectors
    // const toggleProgressBarVisibility = (show) => {
    //     const stepsBar = document.querySelector('.row.text-center.mb-4, .d-flex.align-items-center.mb-4');
    //     if (stepsBar) {
    //         stepsBar.style.display = show ? '' : 'none';
    //     }
    //     if (wizardHeader) {
    //         wizardHeader.style.display = show ? '' : 'none';
    //     }
    // };

    const renderStep1_Welcome = () => {
        // Option B: Hide progress bar and gray header bar on the Welcome screen (Step 0)
        toggleProgressBarVisibility(false);

        updateWizardFooter('Select a scanning method to find PiSelfhosting devices on your network.');

        const savedSubnet = lastSubnetInput || '';

        wizardBody.innerHTML = `
            <div class="text-center">
                <div class="mb-4">
                    <!-- Custom 300x300 high-res brand logo centered on Step 0 Onboarding -->
                    <img src="/static/images/piselfhosting-icon512x512.png"
                         alt="PiSelfhosting Logo"
                         style="width: 350px; height: 350px;">
                </div>
                <h2 class="h4">Network Discovery</h2>
                <p class="text-muted small">We need to find the Raspberry Pi(s) on your network to begin.</p>

                <div class="card card-body bg-light text-start mx-auto mb-4" style="max-width: 500px;">
                    <div class="form-check mb-2">
                        <input class="form-check-input" type="radio" name="scanMethod" id="autoDetectRadio" checked>
                        <label class="form-check-label" for="autoDetectRadio">
                            <strong>Auto-Detect (Recommended)</strong>
                            <span class="d-block small text-muted">Scans your current local subnet automatically.</span>
                        </label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="scanMethod" id="manualScanRadio">
                        <label class="form-check-label" for="manualScanRadio">
                            <strong>Manual Subnet Scan</strong>
                            <span class="d-block small text-muted">Use this if you are on a different VLAN or VPN.</span>
                        </label>
                    </div>
                    <div class="mt-3">
                        <input type="text" id="manualSubnetInput" class="form-control" placeholder="e.g. 192.168.1.0/24" value="${escapeHTML(savedSubnet)}" disabled aria-label="Manual subnet input">
                    </div>
                </div>

                <div class="d-grid gap-2 col-8 mx-auto my-4">
                    <button id="begin-scan-btn" class="btn btn-primary btn-lg">
                        <i class="fa-solid fa-search me-2"></i> Begin Scan
                    </button>
                </div>
            </div>
        `;
        setupStep1();
    };

    /** @param {ScanData} scanData */
    const renderStep2_ConfigureDevices = (scanData) => {
        // Option B: Visual progress bar and header bar start here!
        toggleProgressBarVisibility(true);
        if (wizardHeader) {
            wizardHeader.innerHTML = '<strong>Step 1 of 4: Discovery &amp; SSH</strong>';
        }
        updateWizardFooter('Enter the SSH credentials for the devices you want to manage.');
        const popoverContent = `
            The scanner looks for two types of devices:
            1. Physical Raspberry Pis by checking for a hardware model file.
            2. PiSelfhosting Virtual Pis by checking for the
               '/etc/piselfhosting-virtual-pi-server' file inside the guest OS.
        `.trim();
        wizardBody.innerHTML = `
            <div class="text-start">
                <h2 class="h4 text-center">
                    Device Configuration
                    <i class="fa-solid fa-circle-question text-muted ms-2" style="font-size: 0.8em; cursor: pointer;"
                       data-bs-toggle="popover" data-bs-trigger="hover focus"
                       data-bs-title="How Detection Works"
                       data-bs-content="${escapeHTML(popoverContent)}"></i>
                </h2>
                <p class="text-muted text-center small mb-4">
                    Found ${scanData.hosts.length} potential Pi network interfaces.
                    Provide credentials for each device to get more details.
                </p>
                <div class="card card-body bg-light mb-4">
                    <h3 class="h6">Common Actions</h3>
                    <p class="small text-muted">
                        Use these fields to apply credentials to all devices, or to clear all selections.
                    </p>
                    <div class="row g-2">
                        <div class="col-sm-4">
                            <input type="text" class="form-control form-control-sm" id="master-username" placeholder="Username">
                        </div>
                        <div class="col-sm-4">
                            <input type="password" class="form-control form-control-sm" id="master-password" placeholder="Password">
                        </div>
                        <div class="col-sm-2 d-grid">
                            <button class="btn btn-secondary btn-sm" id="apply-to-all-btn">Apply</button>
                        </div>
                        <div class="col-sm-2 d-grid">
                            <button class="btn btn-outline-secondary btn-sm" id="deselect-all-btn">Clear All</button>
                        </div>
                    </div>
                </div>
                <div id="device-cards-container" class="row row-cols-1 row-cols-md-2 row-cols-lg-3 row-cols-xl-4 g-4"></div>
                <div class="d-grid gap-2 col-8 mx-auto my-4" id="step2-action-area"></div>
            </div>
        `;
        const container = document.getElementById('device-cards-container');
        scanData.hosts.forEach((host, index) => {
            const cachedDevice = managedDeviceCache[host.ip];
            const isManaged = !!cachedDevice;
            const savedUser = cachedDevice ? cachedDevice.username : '';
            const savedPass = cachedDevice ? cachedDevice.password : '';

            const cardWrapper = document.createElement('div');
            cardWrapper.className = 'col';

            const card = document.createElement('div');
            card.className = 'card h-100 device-card shadow-sm';
            card.dataset.ip = host.ip;
            card.dataset.hostname = host.hostname || 'Unknown Host';

            const header = document.createElement('div');
            header.className = 'card-header bg-light';

            const title = document.createElement('div');
            title.className = 'fw-bold text-truncate mb-2';
            title.title = host.hostname || 'Unknown Host';

            const serverIcon = document.createElement('i');
            serverIcon.className = 'fa-solid fa-server me-2';
            title.appendChild(serverIcon);
            title.appendChild(document.createTextNode(host.hostname || 'Unknown Host'));

            const formCheck = document.createElement('div');
            formCheck.className = 'form-check form-switch';

            const switchInput = document.createElement('input');
            switchInput.className = 'form-check-input';
            switchInput.type = 'checkbox';
            switchInput.role = 'switch';
            switchInput.id = `manageDeviceSwitch-${index}`;
            switchInput.checked = isManaged;

            const switchLabel = document.createElement('label');
            switchLabel.className = 'form-check-label';
            switchLabel.htmlFor = `manageDeviceSwitch-${index}`;
            switchLabel.textContent = 'Manage';

            formCheck.appendChild(switchInput);
            formCheck.appendChild(switchLabel);

            header.appendChild(title);
            header.appendChild(formCheck);

            const body = document.createElement('div');
            body.className = 'card-body d-flex flex-column';

            const ipMacDiv = document.createElement('div');
            ipMacDiv.className = 'mb-3';

            const ipDiv = document.createElement('div');
            ipDiv.className = 'fw-bold text-primary';
            ipDiv.style.fontSize = '1.1rem';
            ipDiv.textContent = `IP: ${host.ip}`;

            const macDiv = document.createElement('div');
            macDiv.className = 'text-muted small';
            macDiv.textContent = `MAC: ${host.mac}`;

            ipMacDiv.appendChild(ipDiv);
            ipMacDiv.appendChild(macDiv);

            const rowG2 = document.createElement('div');
            rowG2.className = 'row g-2';

            const colUsername = document.createElement('div');
            colUsername.className = 'col-sm-6';
            const usernameInput = document.createElement('input');
            usernameInput.type = 'text';
            usernameInput.className = 'form-control form-control-sm device-username';
            usernameInput.placeholder = 'Username';
            usernameInput.value = savedUser;
            usernameInput.disabled = !isManaged;
            colUsername.appendChild(usernameInput);

            const colPassword = document.createElement('div');
            colPassword.className = 'col-sm-6';
            const passwordInput = document.createElement('input');
            passwordInput.type = 'password';
            passwordInput.className = 'form-control form-control-sm device-password';
            passwordInput.placeholder = 'Password';
            passwordInput.value = savedPass;
            passwordInput.disabled = !isManaged;
            colPassword.appendChild(passwordInput);

            rowG2.appendChild(colUsername);
            rowG2.appendChild(colPassword);

            const hwDetails = document.createElement('div');
            hwDetails.className = 'hardware-details mt-auto pt-3';
            hwDetails.style.fontSize = '0.8rem';
            hwDetails.style.display = isManaged ? 'block' : 'none';

            if (isManaged && cachedDevice) {
                const hr = document.createElement('hr');
                hr.className = 'my-2';
                hwDetails.appendChild(hr);

                const serialSpan = document.createElement('span');
                const chipIcon = document.createElement('i');
                chipIcon.className = 'fa-solid fa-microchip me-1';
                serialSpan.appendChild(chipIcon);
                serialSpan.appendChild(document.createTextNode(` Serial: ${cachedDevice.serial || 'N/A'}`));
                hwDetails.appendChild(serialSpan);
                hwDetails.appendChild(document.createElement('br'));

                const ramSpan = document.createElement('span');
                const ramIcon = document.createElement('i');
                ramIcon.className = 'fa-solid fa-memory me-1';
                ramSpan.appendChild(ramIcon);
                ramSpan.appendChild(document.createTextNode(` RAM: ${cachedDevice.ram || 'N/A'}`));
                hwDetails.appendChild(ramSpan);
                hwDetails.appendChild(document.createElement('br'));

                const diskInfo = cachedDevice.disks && cachedDevice.disks.length > 0 ? cachedDevice.disks.find(d => d.mounted_on === '/') : null;
                const diskSpan = document.createElement('span');
                const diskIcon = document.createElement('i');
                diskIcon.className = 'fa-solid fa-hard-drive me-1';
                diskSpan.appendChild(diskIcon);
                const diskText = diskInfo ? ` Disk: ${diskInfo.size} (${diskInfo.pcent} used)` : ' Disk: N/A';
                diskSpan.appendChild(document.createTextNode(diskText));
                hwDetails.appendChild(diskSpan);
            }

            body.appendChild(ipMacDiv);
            body.appendChild(rowG2);
            body.appendChild(hwDetails);

            const footer = document.createElement('div');
            footer.className = 'card-footer text-body-secondary small';
            footer.appendChild(document.createTextNode('Status: '));
            const statusSpan = document.createElement('span');
            statusSpan.className = 'status-text';
            if (isManaged && cachedDevice) {
                statusSpan.className = 'status-text text-success fw-bold';
                statusSpan.textContent = `Success! (Model: ${cachedDevice.model || 'Unknown Model'})`;
            } else {
                statusSpan.textContent = 'Pending credentials...';
            }
            footer.appendChild(statusSpan);

            card.appendChild(header);
            card.appendChild(body);
            card.appendChild(footer);

            cardWrapper.appendChild(card);
            container.appendChild(cardWrapper);
        });

        document.querySelectorAll('.device-card').forEach(card => {
            const manageSwitch = /** @type {HTMLInputElement} */ (card.querySelector('[type="checkbox"]'));
            const usernameInput = /** @type {HTMLInputElement} */ (card.querySelector('.device-username'));
            const passwordInput = /** @type {HTMLInputElement} */ (card.querySelector('.device-password'));

            if (manageSwitch && usernameInput && passwordInput) {
                const handleSwitchChange = () => {
                    const isDisabled = !manageSwitch.checked;
                    usernameInput.disabled = isDisabled;
                    passwordInput.disabled = isDisabled;
                    if (manageSwitch.checked) {
                        usernameInput.focus();
                    }
                };
                manageSwitch.addEventListener('change', handleSwitchChange);

                [usernameInput, passwordInput].forEach(input => {
                    input.addEventListener('input', () => {
                        if (!manageSwitch.checked && input.value.length > 0) {
                            manageSwitch.checked = true;
                            handleSwitchChange();
                        }
                    });
                });
                handleSwitchChange();
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

        // Set up the Back/Proceed action buttons dynamically
        const actionWrapper = document.createElement('div');
        actionWrapper.className = 'd-flex justify-content-center gap-2 my-4';

        const backBtn = document.createElement('button');
        backBtn.id = 'back-to-step1-btn';
        backBtn.className = 'btn btn-outline-secondary btn-lg';
        backBtn.innerHTML = '<i class="fa-solid fa-arrow-left me-2"></i>Back';
        backBtn.addEventListener('click', renderStep1_Welcome);
        actionWrapper.appendChild(backBtn);

        const getDetailsBtn = document.createElement('button');
        getDetailsBtn.id = 'get-details-btn';
        getDetailsBtn.className = 'btn btn-primary btn-lg';
        getDetailsBtn.innerHTML = '<i class="fa-solid fa-plug-circle-check me-2"></i>Connect & Get Details';
        getDetailsBtn.addEventListener('click', handleGetDeviceDetails);
        actionWrapper.appendChild(getDetailsBtn);

        if (Object.keys(managedDeviceCache).length > 0) {
            const proceedBtn = document.createElement('button');
            proceedBtn.id = 'proceed-to-step3-btn';
            proceedBtn.className = 'btn btn-success btn-lg';
            proceedBtn.innerHTML = '<i class="fa-solid fa-arrow-right-to-bracket me-2"></i>Proceed';
            proceedBtn.addEventListener('click', renderStep3_SelectSoftware);
            actionWrapper.appendChild(proceedBtn);
        }

        const step2ActionArea = document.getElementById('step2-action-area');
        if (step2ActionArea) {
            step2ActionArea.textContent = '';
            step2ActionArea.appendChild(actionWrapper);
        }

        const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
        Array.from(popoverTriggerList).forEach(el => new bootstrap.Popover(el, {}));
    };

    const handleGetDeviceDetails = async () => {
        managedDeviceCache = {};
        const step2ActionArea = document.getElementById('step2-action-area');
        const getDetailsBtn = document.getElementById('get-details-btn');
        setButtonState(getDetailsBtn, true, {loadingText: 'Connecting...'});

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
            detailsEl.textContent = '';
            statusEl.className = 'status-text text-primary';
            statusEl.textContent = 'Connecting...';

            const promise = fetchAPI('/get-device-details', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ip, username, password})
            })
                .then(data => {
                    /** @type {DeviceDetails} */
                    const details = data.details || data;

                    statusEl.className = 'status-text text-success fw-bold';
                    statusEl.textContent = `Success! (Model: ${details.model || 'Unknown Model'})`;
                    managedDeviceCache[ip] = { ...details, ip, username, password, hostname };

                    const diskInfo = details.disks && details.disks.length > 0 ? details.disks.find(d => d.mounted_on === '/') : null;

                    const hr = document.createElement('hr');
                    hr.className = 'my-2';
                    detailsEl.appendChild(hr);

                    const serialSpan = document.createElement('span');
                    const chipIcon = document.createElement('i');
                    chipIcon.className = 'fa-solid fa-microchip me-1';
                    serialSpan.appendChild(chipIcon);
                    serialSpan.appendChild(document.createTextNode(` Serial: ${details.serial || 'N/A'}`));
                    detailsEl.appendChild(serialSpan);
                    detailsEl.appendChild(document.createElement('br'));

                    const ramSpan = document.createElement('span');
                    const ramIcon = document.createElement('i');
                    ramIcon.className = 'fa-solid fa-memory me-1';
                    ramSpan.appendChild(ramIcon);
                    ramSpan.appendChild(document.createTextNode(` RAM: ${details.ram || 'N/A'}`));
                    detailsEl.appendChild(ramSpan);
                    detailsEl.appendChild(document.createElement('br'));

                    const diskSpan = document.createElement('span');
                    const diskIcon = document.createElement('i');
                    diskIcon.className = 'fa-solid fa-hard-drive me-1';
                    diskSpan.appendChild(diskIcon);
                    const diskText = diskInfo ? ` Disk: ${diskInfo.size} (${diskInfo.pcent} used)` : ' Disk: N/A';
                    diskSpan.appendChild(document.createTextNode(diskText));
                    detailsEl.appendChild(diskSpan);

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

        const actionWrapper = document.createElement('div');
        actionWrapper.className = 'd-flex justify-content-center gap-2 my-4';

        const backBtn = document.createElement('button');
        backBtn.id = 'back-to-step1-btn';
        backBtn.className = 'btn btn-outline-secondary btn-lg';
        backBtn.innerHTML = '<i class="fa-solid fa-arrow-left me-2"></i>Back';
        backBtn.addEventListener('click', renderStep1_Welcome);
        actionWrapper.appendChild(backBtn);

        actionWrapper.appendChild(getDetailsBtn);

        if (Object.keys(managedDeviceCache).length > 0) {
            const proceedBtn = document.createElement('button');
            proceedBtn.id = 'proceed-to-step3-btn';
            proceedBtn.className = 'btn btn-success btn-lg';
            proceedBtn.innerHTML = '<i class="fa-solid fa-arrow-right-to-bracket me-2"></i>Proceed';
            proceedBtn.addEventListener('click', renderStep3_SelectSoftware);
            actionWrapper.appendChild(proceedBtn);

            updateWizardFooter(`Found ${Object.keys(managedDeviceCache).length} manageable device(s). Ready to proceed.`, 'success');
        } else {
            updateWizardFooter('No devices could be contacted. Check credentials and click "Try Again".', 'danger');
        }

        setButtonState(getDetailsBtn, false, {text: '<i class="fa-solid fa-plug-circle-check me-2"></i>Try Again'});
        if (step2ActionArea) {
            step2ActionArea.textContent = '';
            step2ActionArea.appendChild(actionWrapper);
        }
    };

    /** @param {Component} component
     * @param {string} groupName
     * @param {string} type
     */
    const createComponentInput = (component, groupName, type) => {
        const escapedId = escapeHTML(component.id);
        const escapedName = escapeHTML(component.name);
        const escapedDesc = escapeHTML(component.description);
        const escapedGroupName = escapeHTML(groupName);

        const inputName = type === 'radio' ? `group-${escapedGroupName}` : `component-${escapedId}`;
        const checkedAttr = (component.default || selectedComponentsCache.includes(component.id)) ? 'checked' : '';

        return `
            <div class="form-check mb-2">
                <input class="form-check-input" type="${type}" name="${inputName}"
                       value="${escapedId}" id="comp-${escapedId}" ${checkedAttr}>
                <label class="form-check-label" for="comp-${escapedId}"><strong>${escapedName}</strong></label>
            </div>
            <p class="card-text small text-muted ms-4 mb-3">${escapedDesc}</p>
        `;
    };

    const renderStep3_SelectSoftware = async () => {
        wizardHeader.innerHTML = '<strong>Step 2 of 4: Select Software</strong>';
        wizardBody.innerHTML = `
            <div class="text-center">
                <i class="fa-solid fa-spinner fa-spin fa-2x text-muted"></i>
                <p class="mt-2">Loading available software...</p>
            </div>
        `;
        updateWizardFooter('Choose software to install. Selections in a category are mutually exclusive.');

        try {
            /** @type {[SoftwareResponseData, GroupData]} */
            const [softwareData, groupsData] = await Promise.all([
                fetchAPI('/get-available-software', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({devices: Object.values(managedDeviceCache)})
                }),
                fetchAPI('/get-software-groups')
            ]);

            allSoftwareCache = softwareData.available_software;
            const packages = softwareData.available_packages || {};
            const groups = groupsData.groups;
            const allGroupedComponents = new Set(Object.values(groups).flatMap(g => Array.isArray(g) ? g : g.components));

            let tabNavHTML = '<ul class="nav nav-tabs" id="softwareTabs" role="tablist">';
            let tabContentHTML = '<div class="tab-content" id="softwareTabsContent">';
            let active = 'active';

            // Add Packages tab first if packages exist
            if (Object.keys(packages).length > 0) {
                tabNavHTML += `
                    <li class="nav-item" role="presentation">
                        <button class="nav-link ${active}" data-bs-toggle="tab" data-bs-target="#tab-packages" type="button">
                            <i class="fa-solid fa-layer-group me-1"></i> Packages
                        </button>
                    </li>`;
                tabContentHTML += `<div class="tab-pane fade show ${active} p-3" id="tab-packages" role="tabpanel">`;
                tabContentHTML += `<p class="text-muted small mb-3">Select a package to instantly deploy a fully integrated stack of services.</p>`;

                Object.keys(packages).forEach(pkgId => {
                    const pkg = packages[pkgId];
                    const pkgComponents = allSoftwareCache.filter(c => c.package_id === pkgId);
                    const compNames = pkgComponents.map(c => c.name).join(', ');

                    tabContentHTML += `
                        <div class="form-check mb-2">
                            <input class="form-check-input package-checkbox" type="checkbox" name="package-${escapeHTML(pkgId)}"
                                   value="${escapeHTML(pkgId)}" id="pkg-${escapeHTML(pkgId)}" data-components="${escapeHTML(JSON.stringify(pkgComponents.map(c=>c.id)))}">
                            <label class="form-check-label" for="pkg-${escapeHTML(pkgId)}"><strong>${escapeHTML(pkg.name)}</strong></label>
                        </div>
                        <p class="card-text small text-muted ms-4 mb-1">${escapeHTML(pkg.description || 'A pre-configured stack of services.')}</p>
                        <p class="card-text small text-primary ms-4 mb-3"><em>Includes: ${escapeHTML(compNames)}</em></p>
                    `;
                });
                tabContentHTML += `</div>`;
                active = ''; // Remove active status for the rest of the tabs
            }

            Object.keys(groups).forEach((groupName) => {
                const tabId = `tab-${groupName.replace(/\s+/g, '-')}`;
                tabNavHTML += `
                    <li class="nav-item" role="presentation">
                        <button class="nav-link ${active}" data-bs-toggle="tab" data-bs-target="#tab-standalone" type="button">
                            ${escapeHTML(groupName)}
                        </button>
                    </li>`;
                tabContentHTML += `<div class="tab-pane fade show ${active} p-3" id="${tabId}" role="tabpanel">`;

                const groupInfo = groups[groupName];
                const isExclusive = Array.isArray(groupInfo) ? false : groupInfo.is_exclusive;
                const compList = Array.isArray(groupInfo) ? groupInfo : groupInfo.components;
                const inputType = isExclusive ? 'radio' : 'checkbox';

                compList.forEach(compId => {
                    // Safe lookup: gets the id property if compId is an object, otherwise uses compId directly
                    const targetId = typeof compId === 'object' && compId ? compId.id : compId;
                    const component = allSoftwareCache.find(c => c.id === targetId);
                    if (component) {
                        tabContentHTML += createComponentInput(component, groupName, inputType);
                    }
                });
                tabContentHTML += `</div>`;
                active = '';
            });

            tabNavHTML += `
                <li class="nav-item" role="presentation">
                    <button class="nav-link ${active}" data-bs-toggle="tab" data-bs-target="#tab-standalone" type="button">
                        Standalone
                    </button>
                </li>
            `;
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
                    <p class="text-muted text-center small mb-4">
                        Select the software you wish to install on your ${Object.keys(managedDeviceCache).length} selected device(s).
                    </p>
                    ${tabNavHTML}
                    ${tabContentHTML}
                    <div id="step3-action-area"></div>
                </div>
            `;

            // Setup package sync logic
            const updatePackageCheckboxes = () => {
                document.querySelectorAll('.package-checkbox').forEach(pkgCheckbox => {
                    const compIds = JSON.parse((/** @type {HTMLElement} */ (pkgCheckbox)).dataset.components || '[]');
                    if (compIds.length === 0) return;
                    (/** @type {HTMLInputElement} */ (pkgCheckbox)).checked = compIds.every(id => {
                        const compInput = /** @type {HTMLInputElement} */ (document.getElementById(`comp-${id}`));
                        return compInput && compInput.checked;
                    });
                });
            };

            document.querySelectorAll('.package-checkbox').forEach(pkgCheckbox => {
                pkgCheckbox.addEventListener('change', (e) => {
                    const isChecked = (/** @type {HTMLInputElement} */ (e.target)).checked;
                    const compIds = JSON.parse((/** @type {HTMLElement} */ (e.target)).dataset.components || '[]');
                    compIds.forEach(id => {
                        const compInput = /** @type {HTMLInputElement} */ (document.getElementById(`comp-${id}`));
                        if (compInput) compInput.checked = isChecked;
                    });
                });
            });

            document.querySelectorAll('#softwareTabsContent .form-check-input:not(.package-checkbox)').forEach(compCheckbox => {
                compCheckbox.addEventListener('change', updatePackageCheckboxes);
            });
            updatePackageCheckboxes(); // Run once to set initial state

            // Set up action area buttons dynamically with Back navigation
            const actionWrapper = document.createElement('div');
            actionWrapper.className = 'd-flex justify-content-center gap-2 my-4';

            const backBtn = document.createElement('button');
            backBtn.id = 'back-to-step2-btn';
            backBtn.className = 'btn btn-outline-secondary btn-lg';
            backBtn.innerHTML = '<i class="fa-solid fa-arrow-left me-2"></i>Back';
            backBtn.addEventListener('click', () => {
                if (lastScanData) {
                    renderStep2_ConfigureDevices(lastScanData);
                }
            });
            actionWrapper.appendChild(backBtn);

            const proceedBtn = document.createElement('button');
            proceedBtn.id = 'proceed-to-step4-btn';
            proceedBtn.className = 'btn btn-primary btn-lg';
            proceedBtn.innerHTML = '<i class="fa-solid fa-sliders me-2"></i>Configure Services';
            proceedBtn.addEventListener('click', renderStep4_ConfigureServices);
            actionWrapper.appendChild(proceedBtn);

            const step3ActionArea = document.getElementById('step3-action-area');
            if (step3ActionArea) {
                step3ActionArea.appendChild(actionWrapper);
            }

        } catch (error) {
            console.error('Error fetching software list:', error);
            wizardBody.innerHTML = `<p class="text-center text-danger">An error occurred while loading the software list: ${escapeHTML(error.message)}</p>`;
        }
    };

    /** @param {ComponentVariable} variable */
    const createVariableInput = (variable) => {
        const inputId = `var-${escapeHTML(variable.id)}`;
        let inputHTML;

        const savedValue = finalVariablesCache[variable.id] !== undefined
            ? finalVariablesCache[variable.id]
            : (variable.default || '');

        if (variable.source === 'dotenv') {
            const placeholder = '******** (Managed in .env file)';
            inputHTML = `<input type="text" class="form-control form-control-sm" id="${inputId}" name="${escapeHTML(variable.id)}" value="" placeholder="${placeholder}" disabled>`;
        } else if (variable.type === 'select' && variable.options) {
            const optionsHTML = variable.options.map(opt => `<option value="${escapeHTML(opt)}" ${opt === savedValue ? 'selected' : ''}>${escapeHTML(opt)}</option>`).join('');
            inputHTML = `<select class="form-select form-select-sm" id="${inputId}" name="${escapeHTML(variable.id)}">${optionsHTML}</select>`;
        } else {
            const inputType = variable.type === 'password' ? 'password' : 'text';
            inputHTML = `<input type="${inputType}" class="form-control form-control-sm" id="${inputId}" name="${escapeHTML(variable.id)}" value="${escapeHTML(savedValue)}">`;
        }

        return `
            <div class="mb-3">
                <label for="${inputId}" class="form-label"><strong>${escapeHTML(variable.label) || escapeHTML(variable.id)}</strong></label>
                ${inputHTML}
                <div class="form-text small">${escapeHTML(variable.description)}</div>
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
        selectedComponentsCache = Array.from(document.querySelectorAll('#softwareTabsContent .form-check-input:not(.package-checkbox):checked')).map(input => (/** @type {HTMLInputElement} */ (input)).value);
        wizardHeader.innerHTML = '<strong>Step 3 of 4: Configure Services</strong>';
        updateWizardFooter('Provide the required values for your selected software.');

        if (selectedComponentsCache.length === 0) {
            wizardBody.innerHTML = `<p class="text-center text-muted">No software was selected. Please go back and select at least one component.</p>`;
            return;
        }

        wizardBody.innerHTML = `<div class="text-center"><i class="fa-solid fa-spinner fa-spin fa-2x text-muted"></i><p class="mt-2">Loading configuration options...</p></div>`;

        try {
            const data = await fetchAPI('/get-required-variables', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({selected_components: selectedComponentsCache})
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
                        <div id="step4-action-area"></div>
                    </div>
                `;

                const actionWrapper = document.createElement('div');
                actionWrapper.className = 'd-flex justify-content-center gap-2 my-4';

                const backBtn = document.createElement('button');
                backBtn.id = 'back-to-step3-btn';
                backBtn.className = 'btn btn-outline-secondary btn-lg';
                backBtn.innerHTML = '<i class="fa-solid fa-arrow-left me-2"></i>Back';
                backBtn.addEventListener('click', renderStep3_SelectSoftware);
                actionWrapper.appendChild(backBtn);

                const reviewBtn = document.createElement('button');
                reviewBtn.id = 'review-selection-btn';
                reviewBtn.className = 'btn btn-primary btn-lg';
                reviewBtn.innerHTML = '<i class="fa-solid fa-clipboard-check me-2"></i>Review and Confirm';
                reviewBtn.addEventListener('click', handleReviewSelection);
                actionWrapper.appendChild(reviewBtn);

                const step4ActionArea = document.getElementById('step4-action-area');
                if (step4ActionArea) {
                    step4ActionArea.appendChild(actionWrapper);
                }
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
                navPillsHTML += `<button class="nav-link text-start ${activeClass}" data-bs-toggle="pill" data-bs-target="#${tabId}" type="button">${escapeHTML(fullComponentData.name)}</button>`;
                tabContentHTML += `<div class="tab-pane fade show ${activeClass}" id="${tabId}" role="tabpanel">`;

                if (componentWithVars?.variables?.length > 0) {
                    componentWithVars.variables.forEach(v => {
                        tabContentHTML += createVariableInput(v);
                    });
                } else {
                    tabContentHTML += '<p class="text-center text-muted pt-4">This component requires no variable configuration.</p>';
                }

                // Restore previously checked checkboxes for clean install and restart options
                const savedCleanChecked = componentsToCleanCache.includes(compId) ? 'checked' : '';
                const savedRestartChecked = componentsToRestartCache.includes(compId) ? 'checked' : '';

                tabContentHTML += `
                    <hr>
                    <div class="form-check mt-3">
                        <input class="form-check-input clean-install-checkbox" type="checkbox" id="clean-install-checkbox-${compId}" data-comp-id="${compId}" ${savedCleanChecked}>
                        <label class="form-check-label" for="clean-install-checkbox-${compId}">
                            <strong>Perform a clean reinstallation</strong>
                        </label>
                        <div class="form-text small">
                            This will permanently delete all existing data and settings for this service before deploying.
                        </div>
                    </div>`;

                if (fullComponentData.post_install_restart_option) {
                    tabContentHTML += `
                        <div class="form-check mt-3">
                            <input class="form-check-input restart-checkbox" type="checkbox" id="restart-checkbox-${compId}" data-comp-id="${compId}" ${savedRestartChecked}>
                            <label class="form-check-label" for="restart-checkbox-${compId}">
                                <strong>Restart container after installation</strong>
                            </label>
                            <div class="form-text small">
                                Recommended for services that require a restart to initialize properly.
                            </div>
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
                    <p class="text-muted text-center small mb-4">
                        Provide the required settings for your selected software.
                    </p>
                    <div class="row">
                        <div class="col-md-3">${navPillsHTML}</div>
                        <div class="col-md-9"><div id="variables-container">${tabContentHTML}</div></div>
                    </div>
                    <div class="d-grid gap-2 col-8 mx-auto my-4" id="step4-action-area"></div>
                </div>
            `;

            // Set up action area buttons dynamically with Back navigation
            const actionWrapper = document.createElement('div');
            actionWrapper.className = 'd-flex justify-content-center gap-2 my-4';

            const backBtn = document.createElement('button');
            backBtn.id = 'back-to-step3-btn';
            backBtn.className = 'btn btn-outline-secondary btn-lg';
            backBtn.innerHTML = '<i class="fa-solid fa-arrow-left me-2"></i>Back';
            backBtn.addEventListener('click', renderStep3_SelectSoftware);
            actionWrapper.appendChild(backBtn);

            const reviewBtn = document.createElement('button');
            reviewBtn.id = 'review-selection-btn';
            reviewBtn.className = 'btn btn-primary btn-lg';
            reviewBtn.innerHTML = '<i class="fa-solid fa-clipboard-check me-2"></i>Review and Confirm';
            reviewBtn.addEventListener('click', handleReviewSelection);
            actionWrapper.appendChild(reviewBtn);

            const step4ActionArea = document.getElementById('step4-action-area');
            if (step4ActionArea) {
                const configErrorDisplay = document.createElement('div');
                configErrorDisplay.id = 'config-error-display';
                configErrorDisplay.className = 'alert alert-danger';
                configErrorDisplay.style.display = 'none';
                configErrorDisplay.setAttribute('role', 'alert');
                step4ActionArea.appendChild(configErrorDisplay);
                step4ActionArea.appendChild(actionWrapper);
            }

            addRealTimeValidation();
        } catch (error) {
            console.error('Error fetching variables:', error);
            wizardBody.innerHTML = `<p class="text-center text-danger">An error occurred while loading configuration options: ${escapeHTML(error.message)}</p>`;
        }
    };

    /** @param {SystemAnalysisResponse} analysisData */
    const displayAnalysisResults = (analysisData) => {
        let warningsHTML = '';
        let expectedChangesHTML = '';
        let blockingConflictsHTML = '';
        let isBlocked = false;

        analysisData.resource_warnings?.forEach(w => {
            warningsHTML += `
                <li class="list-group-item">
                    <i class="fa-solid fa-triangle-exclamation text-warning me-2"></i>
                    <strong>${escapeHTML(w.type)} Warning:</strong> ${escapeHTML(w.message)}
                </li>`;
        });

        analysisData.external_conflicts?.ports?.forEach(p => {
            if (p.conflict_type === 'EXPECTED_REINSTALLATION') {
                expectedChangesHTML += `
                    <li class="list-group-item">
                        <i class="fa-solid fa-arrows-rotate text-info me-2"></i>
                        <strong>Port ${p.port} Re-use:</strong>
                        The existing service <strong>${escapeHTML(p.conflicting_service)}</strong> will be stopped and replaced by
                        <strong>${escapeHTML(p.proposed_service)}</strong>.
                    </li>`;
            } else {
                isBlocked = true;
                const icon = p.conflict_type === 'DANGEROUS_NATIVE_PROCESS_CONFLICT' ? 'fa-shield-halved' : 'fa-network-wired';
                blockingConflictsHTML += `
                    <li class="list-group-item">
                        <i class="fa-solid ${icon} text-danger me-2"></i>
                        <strong>Port ${p.port} Conflict:</strong>
                        This port is already in use by a critical service: <strong>${escapeHTML(p.conflicting_service)}</strong>.
                        You must change the port for <strong>${escapeHTML(p.proposed_service)}</strong> to continue.
                    </li>`;
            }
        });

        analysisData.external_conflicts?.volumes?.forEach(v => {
            warningsHTML += `
                <li class="list-group-item">
                    <i class="fa-solid fa-folder-open text-warning me-2"></i>
                    <strong>Shared Volume:</strong> The path <strong>${escapeHTML(v.volume_path)}</strong> is already in use and
                    will be shared with <strong>${escapeHTML(v.proposed_service)}</strong>. This is usually safe but be aware.
                </li>`;
        });

        const modalBodyHTML = `
            ${isBlocked ? `
                <div class="alert alert-danger" role="alert">
                    <h4 class="alert-heading">Action Required</h4>
                    <p>One or more blocking conflicts were detected. Please review the items below and adjust your
                       configuration before proceeding.</p>
                </div>` : ''}
            ${blockingConflictsHTML ? `
                <h5><i class="fa-solid fa-ban me-2"></i>Blocking Conflicts</h5>
                <ul class="list-group mb-4">${blockingConflictsHTML}</ul>` : ''}
            ${expectedChangesHTML ? `
                <h5><i class="fa-solid fa-info-circle me-2"></i>Expected Changes</h5>
                <ul class="list-group mb-4">${expectedChangesHTML}</ul>` : ''}
            ${warningsHTML ? `
                <h5><i class="fa-solid fa-triangle-exclamation me-2"></i>Warnings</h5>
                <ul class="list-group mb-2">${warningsHTML}</ul>` : ''}
            ${!blockingConflictsHTML && !expectedChangesHTML && !warningsHTML ? `
                <p class="text-center text-success">
                    <i class="fa-solid fa-check-circle me-2"></i>
                    No conflicts or warnings found. Your configuration looks good to go!
                </p>` : ''}
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
                    <button type="button" class="btn btn-primary" id="modal-proceed-btn" ${isBlocked ? 'disabled' : ''}>
                        ${isBlocked ? 'Cannot Proceed' : 'Proceed to Confirmation'}
                    </button>
                  </div>
                </div>
              </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        const modalEl = document.querySelector('#analysis-modal');
        const proceedBtn = document.querySelector('#modal-proceed-btn');

        if (!modalEl || !proceedBtn) return;
        // @ts-ignore
        const analysisModal = new bootstrap.Modal(modalEl);

        proceedBtn.addEventListener('click', () => {
           /** @type {any} */ (analysisModal).hide();
            renderStep5_Confirmation();
        });
        /** @type {any} */ (analysisModal)["show" ]();
    };

    const handleReviewSelection = async () => {
        if (!validateConfiguration()) return;

        const reviewBtn = document.getElementById('review-selection-btn');
        const errorDiv = document.getElementById('config-error-display');
        setButtonState(reviewBtn, true, {loadingText: 'Analyzing...'});

        finalVariablesCache = {};
        document.querySelectorAll('#variables-container [name]:not(:disabled)').forEach(input => {
            const el = /** @type {HTMLInputElement|HTMLSelectElement} */ (input);
            finalVariablesCache[el.name] = el.value;
        });

        componentsToCleanCache = Array.from(document.querySelectorAll('.clean-install-checkbox:checked')).map(cb => (/** @type {HTMLElement} */ (cb)).dataset.compId);
        componentsToRestartCache = Array.from(document.querySelectorAll('.restart-checkbox:checked')).map(cb => (/** @type {HTMLElement} */ (cb)).dataset.compId);

        const componentsPayload = selectedComponentsCache.map(compId => {
            const componentData = allSoftwareCache.find(c => c.id === compId);
            const component = {id: compId, name: componentData?.name || compId, ports: [], volumes: []};
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
                headers: {'Content-Type': 'application/json'},
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
                analysisResultsCache = analysisData;
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
        wizardHeader.innerHTML = '<strong>Step 4 of 4: Confirmation</strong>';
        updateWizardFooter('Please review your selections before generating files and deploying.');

        // Mitigation: string-fallbacks ensure we always pass a pure string to escapeHTML
        const devicesHTML = Object.values(managedDeviceCache).map(device => {
            const safeHostname = escapeHTML(device.hostname || 'Unknown Host');
            const safeIp = escapeHTML(device.ip || '0.0.0.0');
            return `<li><strong>${safeHostname}</strong> (${safeIp})</li>`;
        }).join('');

        const softwareHTML = selectedComponentsCache.map(compId => {
            const component = allSoftwareCache.find(c => c.id === compId);
            const safeName = escapeHTML(component?.name || 'Unknown');
            const safeDesc = escapeHTML(component?.description || 'No description.');
            return `<li><strong>${safeName}</strong>: ${safeDesc}</li>`;
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
                <div class="d-grid gap-2 col-8 mx-auto my-4" id="step5-action-area"></div>
            </div>`;

        // Set up action area buttons dynamically with Back navigation
        const actionWrapper = document.createElement('div');
        actionWrapper.className = 'd-flex justify-content-center gap-2 my-4';

        const backBtn = document.createElement('button');
        backBtn.id = 'back-to-step4-btn';
        backBtn.className = 'btn btn-outline-secondary btn-lg';
        backBtn.innerHTML = '<i class="fa-solid fa-arrow-left me-2"></i>Back';
        backBtn.addEventListener('click', renderStep4_ConfigureServices);
        actionWrapper.appendChild(backBtn);

        const finalBtn = document.createElement('button');
        finalBtn.id = 'final-generate-btn';
        finalBtn.className = 'btn btn-success btn-lg';
        finalBtn.innerHTML = '<i class="fa-solid fa-file-invoice me-2"></i>Generate Configuration Files';
        finalBtn.addEventListener('click', handleInstallation);
        actionWrapper.appendChild(finalBtn);

        const step5ActionArea = document.getElementById('step5-action-area');
        if (step5ActionArea) {
            step5ActionArea.appendChild(actionWrapper);
        }
    };

    const handleInstallation = async () => {
        const installBtn = document.getElementById('final-generate-btn');
        setButtonState(installBtn, true, {loadingText: 'Generating files...'});

        try {
            const result = await fetchAPI('/start-installation', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
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
                    <div class="card card-body bg-light text-start my-3">
                        <pre><code id="output-path-display">${escapeHTML(result.output_path)}</code></pre>
                    </div>
                    <div id="final-actions-container">
                         <div class="d-grid gap-2 d-md-flex justify-content-md-center mt-4" id="deployment-actions">
                            <button id="deploy-button" class="btn btn-primary">
                                <i class="fa-solid fa-rocket me-2"></i>Deploy to Pi(s)
                            </button>
                            <button id="start-over-btn" class="btn btn-secondary">Start Over</button>
                        </div>
                    </div>
                    <div id="log-viewer-container" class="mt-4 text-start" style="display: none;">
                        <h3 class="h5 text-center">Deployment Progress</h3>
                        <div class="card">
                            <div class="card-body bg-dark text-white rounded"
                                 style="font-family: monospace; font-size: 0.9em; max-height: 400px; overflow-y: auto;">
                                <pre id="log-output" class="mb-0" style="white-space: pre-wrap;"></pre>
                            </div>
                        </div>
                    </div>
                </div>`;
            document.getElementById('deploy-button').addEventListener('click', () => {
                const outputPath = document.getElementById('output-path-display').textContent;
                handleDeployment(outputPath);
            });
            document.getElementById('start-over-btn').addEventListener('click', renderStep1_Welcome);
        } catch (error) {
            console.error('Installation failed:', error);
            wizardHeader.innerHTML = '<strong>Generation Failed</strong>';
            updateWizardFooter('The process could not be completed.', 'danger');

            let reportText = 'An unknown error occurred.';
            if (error.details && Array.isArray(error.details) && error.details.length > 0) {
                reportText = error.details[0].details || error.details[0].summary || error.message;
            } else if (error.message) {
                reportText = error.message;
            }

            const GITHUB_REPO_URL = "https://github.com/HenkVanHoek/PiSelfhosting";
            const issueBody = encodeURIComponent(
                `**Error Details:**\n\n\`\`\`\n${reportText}\n\`\`\`\n\n` +
                `**Context:**\n- Selected Components: ${selectedComponentsCache.join(', ')}`
            );
            const githubIssueURL = `${GITHUB_REPO_URL}/issues/new?title=` +
                `${encodeURIComponent("Configurator UI Error Report")}&body=${issueBody}`;
            wizardBody.innerHTML = `
                <div class="text-center">
                    <i class="fa-solid fa-circle-xmark fa-3x text-danger mb-3"></i>
                    <h2 class="h4">File Generation Failed</h2>
                    <p class="text-muted">An error occurred during the file generation process.</p>
                    <div class="accordion my-3" id="errorAccordion">
                      <div class="accordion-item">
                        <h2 class="accordion-header">
                            <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse"
                                    data-bs-target="#collapseOne">
                                <strong>Click to view detailed error report</strong>
                            </button>
                        </h2>
                        <div id="collapseOne" class="accordion-collapse collapse" data-bs-parent="#errorAccordion">
                            <div class="accordion-body text-start">
                                <p class="small text-muted">Please copy the full text below when reporting an issue.</p>
                                <textarea class="form-control" rows="8" readonly>` +
                `**Error Details:**\n\n${escapeHTML(reportText)}</textarea>
                            </div>
                        </div>
                      </div>
                    </div>
                    <p class="text-muted small mt-4">This may be a known issue. Please check the Q&A section.</p>
                    <div class="d-grid gap-2 col-8 mx-auto mt-2">
                        <a href="${GITHUB_REPO_URL}/discussions" target="_blank" class="btn btn-info">
                            <i class="fa-solid fa-comments me-2"></i>Check Q&A / Discussions
                        </a>
                        <a href="${githubIssueURL}" target="_blank" class="btn btn-outline-secondary">
                            <i class="fa-brands fa-github me-2"></i>Report Issue on GitHub
                        </a>
                        <button id="start-over-fail-btn" class="btn btn-primary mt-2">Start Over</button>
                    </div>
                </div>`;
            document.getElementById('start-over-fail-btn').addEventListener('click', renderStep1_Welcome);
        }
    };

    /** @param {string} outputPath */
    const handleDeployment = async (outputPath) => {
        const deployButton = document.getElementById('deploy-button');
        const logContainer = document.getElementById('log-viewer-container');
        const logOutput = document.getElementById('log-output');

        setButtonState(deployButton, true, {loadingText: 'Deploying...'});
        logContainer.style.display = 'block';
        logOutput.innerHTML = '';
        wizardHeader.innerHTML = '<strong>Deploying The Services</strong>';
        updateWizardFooter('Deploying services to your Raspberry Pi(s)...', 'primary');

        try {
            const selectedComponentsData = selectedComponentsCache
                .map(id => allSoftwareCache.find(c => c.id === id))
                .filter(Boolean);

            /** @type {DeploymentResponse} */
            const data = await fetchAPI('/deploy-configuration', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    output_path: outputPath,
                    devices: Object.values(managedDeviceCache),
                    components_to_clean: componentsToCleanCache,
                    components_to_restart: componentsToRestartCache,
                    analysis_results: analysisResultsCache,
                    selected_components_data: selectedComponentsData,
                    global_vars: finalVariablesCache
                }),
            });

            const taskId = data.task_id;
            const eventSource = new EventSource(`/stream-deployment/${taskId}`);
            let hasErrors = false;

            const watchdogTimer = setTimeout(() => {
                eventSource.close();
                logOutput.innerHTML += '\n<span class="text-danger fw-bold">[ERROR] Connection to server timed out.</span>\n';
                wizardHeader.innerHTML = '<strong>Deployment Failed</strong>';
                updateWizardFooter('Connection timed out. Please check the backend console.', 'danger');
                setButtonState(deployButton, false, {text: '<i class="fa-solid fa-triangle-exclamation me-2"></i>Deployment Failed - Retry?'});
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
                    setButtonState(deployButton, false, {text: '<i class="fa-solid fa-triangle-exclamation me-2"></i>Show Error Report'});
                wizardHeader.innerHTML = '<strong>Deployment Finished with Errors</strong>';
                    updateWizardFooter('Deployment completed, but some steps failed.', 'warning');
                    deployButton.onclick = () => showErrorSummary(taskId);
                } else {
                    setButtonState(deployButton, false, {text: '<i class="fa-solid fa-circle-check me-2"></i>Deployment Finished'});
                wizardHeader.innerHTML = '<strong>Deployment Finished</strong>';
                    updateWizardFooter('Deployment process completed successfully.', 'success');
                    const finalActions = document.getElementById('final-actions-container');
                    if (finalActions) {
                        finalActions.innerHTML = `
                            <div class="d-grid gap-2 col-8 mx-auto my-4">
                                 <button id="show-summary-btn" class="btn btn-info btn-lg">
                                    <i class="fa-solid fa-list-check me-2"></i>Access Your Services
                                 </button>
                            </div>`;
                        document.getElementById('show-summary-btn').addEventListener('click', () => showServicesSummary(taskId));
                    }
                }
            };
        } catch (error) {
            console.error('Failed to start deployment:', error);
            logOutput.innerHTML += `<span class="text-danger fw-bold">ERROR: Failed to initiate deployment. ${escapeHTML(error.message)}\n</span>`;
        wizardHeader.innerHTML = '<strong>Deployment Failed</strong>';
            setButtonState(deployButton, false, {text: '<i class="fa-solid fa-triangle-exclamation me-2"></i>Deployment Failed - Retry?'});
            updateWizardFooter('Could not start deployment process.', 'danger');
        }
    };

    /** @param {string} taskId */
    const showErrorSummary = async (taskId) => {
        const errorBtn = document.getElementById('deploy-button');
        setButtonState(errorBtn, true, {loadingText: 'Fetching Report...'});
        try {
            /** @type {TaskStatus} */
            const taskData = await fetchAPI(`/task-status/${taskId}`);

            let errorsHTML;
            if (taskData.errors && taskData.errors.length > 0) {
                errorsHTML = taskData.errors.map(err => `
                    <div class="list-group-item">
                        <div class="d-flex w-100 justify-content-between">
                            <h6 class="mb-1">${escapeHTML(err.summary || '')}</h6>
                            <small class="text-muted">${escapeHTML(err.timestamp || '')}</small>
                        </div>
                        <p class="mb-1 small"><strong>Type:</strong> ${escapeHTML(err.type || '')}</p>
                        <p class="mb-1 small"><strong>Details:</strong> ${escapeHTML(err.details || '')}</p>
                        <small class="text-muted">Component: ${escapeHTML(err.component_id || '')}</small>
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
                </div>`
            document.body.insertAdjacentHTML('beforeend', modalHTML);

            const errorModalEl = document.getElementById('error-report-modal');

            if (!errorModalEl) return;

            // Mitigation: JSDoc cast converts errorModalEl safely to HTMLElement to avoid parameter mismatch
            const errorModal = new bootstrap.Modal(/** @type {HTMLElement} */ (errorModalEl));
            errorModal["show"]();
        } catch (error) {
            console.error('Failed to fetch error summary:', error);
            updateWizardFooter('Could not retrieve the error report.', 'danger');
        } finally {
            setButtonState(errorBtn, false, {text: '<i class="fa-solid fa-triangle-exclamation me-2"></i>Show Error Report'});
        }
    };

    /** @param {string} taskId */
    const showServicesSummary = async (taskId) => {
        const summaryBtn = document.getElementById('show-summary-btn');
        if (!summaryBtn) return;

        setButtonState(summaryBtn, true, {loadingText: 'Loading...'});
        try {
            const finalData = await fetchAPI(`/task-status/${taskId}`);
            let allLinks = finalData.service_links || [];

            // --- DE BULLETPROOF FALLBACK ---
            if (allLinks.length === 0 && typeof selectedComponentsCache !== 'undefined') {

                const managedIps = Object.keys(managedDeviceCache);
                const piIp = (typeof finalVariablesCache !== 'undefined' && finalVariablesCache['PISelfhosting_HOST_IP'])
                    ? finalVariablesCache['PISelfhosting_HOST_IP']
                    : (managedIps.length > 0 ? managedIps[0] : window.location.hostname);

                selectedComponentsCache.forEach(compId => {
                    const comp = allSoftwareCache.find(c => c.id === compId);
                    if (comp && comp.ui_port_variable) {
                        let port = finalVariablesCache[comp.ui_port_variable];
                        if (!port && comp.required_variables) {
                            const varDef = comp.required_variables.find(v => v.id === comp.ui_port_variable);
                            if (varDef) port = varDef.default;
                        }
                        const protocol = comp.protocol || 'http';
                        if (port) {
                            allLinks.push({
                                name: comp.name,
                                url: `${protocol}://${piIp}:${port}`
                            });
                        }
                    }
                });
            }

            if (allLinks.length > 0) {
                const uniqueLinks = Array.from(new Set(allLinks.map(a => a.url)))
                    .map(url => allLinks.find(a => a.url === url));

                const linksHTML = uniqueLinks
                    .map(link => `<li class="mb-2"><a href="${escapeHTML(link.url)}" target="_blank" class="fw-bold text-decoration-none">${escapeHTML(link.name)}</a><br><code class="text-muted">${escapeHTML(link.url)}</code></li>`)
                    .join('');

                const summaryBox = `
                <div id="service-links-summary" class="card mt-4 text-start shadow-sm border-success">
                    <div class="card-header bg-success text-white fw-bold">
                        <i class="fa-solid fa-rocket me-2"></i>Access Your Services
                    </div>
                    <div class="card-body">
                        <ul class="list-unstyled mb-0">${linksHTML}</ul>
                    </div>
                </div>`;

                document.getElementById('service-links-summary')?.remove();
                document.getElementById('log-viewer-container').insertAdjacentHTML('beforebegin', summaryBox);
                setButtonState(summaryBtn, false, {text: '<i class="fa-solid fa-check me-2"></i>Links Generated'});
            } else {
                setButtonState(summaryBtn, false, {text: 'No Web Interfaces Found'});
            }
        } catch (error) {
            console.error("Failed to show summary:", error);
            setButtonState(summaryBtn, false, {text: 'Error Loading Summary'});
        }
    };

    const setupStep1 = () => {
        const scanBtn = document.getElementById('begin-scan-btn');
        const manualInput = /** @type {HTMLInputElement} */ (document.getElementById('manualSubnetInput'));

        const autoRadio = document.getElementById('autoDetectRadio');
        const manualRadio = document.getElementById('manualScanRadio');

        if (autoRadio) {
            autoRadio.addEventListener('change', (e) => {
                manualInput.disabled = (/** @type {HTMLInputElement} */ (e.target)).checked;
            });
        }

        if (manualRadio) {
            manualRadio.addEventListener('change', (e) => {
                if ((/** @type {HTMLInputElement} */ (e.target)).checked) {
                    manualInput.disabled = false;
                    manualInput.focus();
                }
            });
        }

        const performScan = async () => {
            setButtonState(scanBtn, true, {loadingText: 'Scanning...'});
            updateWizardFooter('Scanning network for Raspberry Pi devices...', 'primary');
            const subnetToScan = (/** @type {HTMLInputElement} */ (document.getElementById('manualScanRadio'))).checked ? manualInput.value : null;

            try {
                /** @type {ScanData} */
                const data = await fetchAPI('/scan-pis', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({subnet: subnetToScan})
                });
                if (data.permissions_error) {
                    const troubleshootingUrl = 'https://github.com/HenkVanHoek/PiSelfhosting/blob/main/docs/TROUBLESHOOTING.md#network-scan-issues';
                    updateWizardFooter(`<strong>Warning:</strong> The scanner may not have required permissions. Please check our <a href='${troubleshootingUrl}' target='_blank'>troubleshooting guide</a>.`, 'warning');
                } else {
                    lastScanData = data; // Cache the scan data
                    if (subnetToScan) lastSubnetInput = subnetToScan; // Cache manual subnet
                    renderStep2_ConfigureDevices(data);
                }
            } catch (error) {
                console.error('An error occurred during the scan:', error);
                updateWizardFooter(`<i class="fa-solid fa-xmark me-2"></i>An error occurred: ${escapeHTML(error.message)}`, 'danger');
            } finally {
                setButtonState(scanBtn, false);
                scanBtn.innerHTML = '<i class="fa-solid fa-search me-2"></i> Begin Scan';
            }
        };

        if (scanBtn) scanBtn.addEventListener('click', performScan);
    };

    // Modern helper to toggle top horizontal progress bar and small logo visibility
    const toggleProgressBarVisibility = (show) => {
        const stepsBar = document.querySelector('.row.text-center.mb-4, .d-flex.align-items-center.mb-4');
        if (stepsBar) {
            stepsBar.style.display = show ? '' : 'none';
        }
        if (wizardHeader) {
            wizardHeader.style.display = show ? '' : 'none';
        }
    };

    // Initialize Onboarding/Welcome Step 0 on page load
    renderStep1_Welcome();
})();
