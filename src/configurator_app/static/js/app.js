/* global bootstrap, EventSource */
document.addEventListener("DOMContentLoaded", () => {
    /** @type {Object.<string, DeviceDetails>} */
    let managedDeviceCache = {};
    /** @type {string[]} */
    let selectedComponentsCache = [];
    /** @type {Component[]} */
    let allSoftwareCache = [];
    /** @type {Object.<string, string>} */
    let finalVariablesCache = {};
    /** @type {string[]} */
    let componentsToCleanCache = [];
    /** @type {string[]} */
    let componentsToRestartCache = [];
    /** @type {SystemAnalysisResponse | {}} */
    let analysisResultsCache = {};

    const wizardHeader = document.getElementById("wizard-header");
    const wizardBody = document.getElementById("wizard-body");

    /** @param {string} url @param {RequestInit} [options] */
    async function fetchAPI(url, options = {}) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                const msg = data.details || data.error || "Request failed.";
                return Promise.reject({ message: msg });
            }
            return response.json();
        } catch (err) {
            return Promise.reject({ message: "Network error." });
        }
    }

    function setButtonState(btn, loading, options = {}) {
        if (!btn) return;
        if (!btn.dataset.text) btn.dataset.text = btn.innerHTML;
        btn.disabled = loading;
        btn.innerHTML = loading ? "Processing..." : (options.text || btn.dataset.text);
    }

    function updateWizardFooter(msg, type = "muted") {
        const el = document.getElementById("wizard-footer");
        if (el) el.innerHTML = "<p class=\"text-" + type + " small\">" + msg + "</p>";
    }

    const syncInheritedCredentials = () => {
        const u = document.getElementById("master-username").value;
        const p = document.getElementById("master-password").value;
        document.querySelectorAll(".device-card").forEach(card => {
            const ovr = card.querySelector(".override-switch");
            if (ovr && !ovr.checked) {
                card.querySelector(".device-username").value = u;
                card.querySelector(".device-password").value = p;
            }
        });
    };

    /** @param {ScanData} data */
    const renderStep2_ConfigureDevices = (data) => {
        wizardHeader.innerHTML = "<strong>Step 2 of 5: Configure Devices</strong>";
        wizardBody.innerHTML = "<div class=\"text-start\"><div class=\"card " +
            "card-body bg-light mb-4\"><h6>Master Credentials</h6><div " +
            "class=\"row g-2\"><div class=\"col-5\"><input type=\"text\" " +
            "id=\"master-username\" class=\"form-control\" placeholder=\"" +
            "User\"></div><div class=\"col-5\"><input type=\"password\" " +
            "id=\"master-password\" class=\"form-control\" placeholder=\"" +
            "Pass\"></div><div class=\"col-2 d-grid\"><button class=\"btn " +
            "btn-outline-secondary\" id=\"deselect-btn\">Clear</button></div>" +
            "</div></div><div id=\"device-cards\" class=\"row row-cols-1 " +
            "row-cols-md-3 g-4\"></div><div class=\"d-grid col-8 mx-auto my-4\">" +
            "<button id=\"details-btn\" class=\"btn btn-primary btn-lg\">" +
            "Retrieve Details</button></div></div>";

        const container = document.getElementById("device-cards");
        data.hosts.forEach((host, idx) => {
            const wrapper = document.createElement("div");
            wrapper.className = "col";
            const hId = "ovr-" + idx;
            wrapper.innerHTML = "<div class=\"card device-card h-100\" style=\"" +
                "opacity: 0.6;\" data-ip=\"" + host.ip + "\" data-h=\"" +
                (host.hostname || "Unknown") + "\"><div class=\"card-body\">" +
                "<div class=\"d-flex justify-content-between mb-2\">" +
                "<h6 class=\"text-truncate\" style=\"flex: 1;\">" +
                (host.hostname || "Unknown") + "</h6><div class=\"form-check " +
                "form-switch\"><input class=\"form-check-input provision-switch\"" +
                " type=\"checkbox\"></div></div><p class=\"small\">" + host.ip +
                "</p><div class=\"credentials-area p-2 bg-light rounded\"><div " +
                "class=\"d-flex justify-content-between small mb-2\"><span>" +
                "SSH</span><div class=\"form-switch\"><input class=\"" +
                "form-check-input override-switch\" type=\"checkbox\" id=\"" +
                hId + "\"> <label for" + "=\"" + hId + "\">Override</label></div>" +
                "</div><input type=\"text\" class=\"form-control form-control-sm " +
                "device-username mb-1\" disabled><input type=\"password\" " +
                "class=\"form-control form-control-sm device-password\" disabled>" +
                "</div><div class=\"hardware-details mt-2 small\" style=\"" +
                "display: none;\"></div></div><div class=\"card-footer small\">" +
                "Status: <span class=\"status-text\">Not selected</span></div></div>";
            container.appendChild(wrapper);
        });

        document.getElementById("master-username").addEventListener("input",
            syncInheritedCredentials);
        document.getElementById("master-password").addEventListener("input",
            syncInheritedCredentials);

        document.querySelectorAll(".device-card").forEach(card => {
            const ovr = card.querySelector(".override-switch");
            const prv = card.querySelector(".provision-switch");
            ovr.addEventListener("change", () => {
                card.querySelector(".device-username").disabled = !ovr.checked;
                card.querySelector(".device-password").disabled = !ovr.checked;
                if (!ovr.checked) syncInheritedCredentials();
            });
            prv.addEventListener("change", () => {
                card.style.opacity = prv.checked ? "1" : "0.6";
                card.querySelector(".status-text").textContent = prv.checked ?
                    "Idle" : "Not selected";
            });
        });

        document.getElementById("deselect-btn").onclick = () => {
            document.querySelectorAll(".provision-switch").forEach(s => {
                const input = /** @type {HTMLInputElement} */ (s);
                input.checked = false;
                input.dispatchEvent(new Event("change"));
            });
        };

        document.getElementById("details-btn").onclick = async () => {
            managedDeviceCache = {};
            const promises = [];
            document.querySelectorAll(".device-card").forEach(card => {
                const prv = /** @type {HTMLInputElement} */ (
                    card.querySelector(".provision-switch")
                );
                if (!prv.checked) return;
                const ip = card.dataset.ip;
                const user = card.querySelector(".device-username").value;
                const pass = card.querySelector(".device-password").value;
                const sEl = card.querySelector(".status-text");
                const dEl = card.querySelector(".hardware-details");
                sEl.textContent = "Connecting...";

                const p = fetchAPI("/get-device-details", {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ip, username: user, password: pass })
                })
                .then(res => {
                    const d = res.details;
                    sEl.textContent = "Connected";
                    managedDeviceCache[ip] = {
                        ip, username: user, password: pass, disks: d.disks,
                        hostname: card.dataset.h, model: d.model,
                        serial: d.serial, ram: d.ram
                    };
                    const dList = /** @type {DiskInfo[]} */ (d.disks || []);
                    const [disk] = dList.filter(e => e.mounted_on === "/");
                    dEl.innerHTML = "<hr>Model: " + d.model + "<br>RAM: " + d.ram;
                    dEl.style.display = "block";
                }).catch(err => { sEl.textContent = "Error: " + err.message; });
                promises.push(p);
            });
            await Promise.allSettled(promises);
            if (Object.keys(managedDeviceCache).length > 0) renderStep3_SelectSoftware();
        };
        syncInheritedCredentials();
    };

    /** @param {Component} c @param {string} g @param {string} t */
    const createComponentInput = (c, g, t) => {
        const name = t === "radio" ? "g-" + g : "c-" + c.id;
        const isChecked = c.default ? "checked" : "";
        const cpId = "cp-" + c.id;
        return "<div class=\"form-check mb-2\"><input class=\"form-check-input\" " +
            "type=\"" + t + "\" name=\"" + name + "\" value=\"" + c.id +
            "\" id=\"" + cpId + "\" " + isChecked + "><label class=\"" +
            "form-check-label\" for" + "=\"" + cpId + "\"><strong>" +
            c.name + "</strong></label></div><p class=\"small text-muted " +
            "ms-4 mb-3\">" + c.description + "</p>";
    };

    const renderStep3_SelectSoftware = async () => {
        wizardHeader.innerHTML = "<strong>Step 3 of 5: Select Software</strong>";
        wizardBody.innerHTML = "<div class=\"text-center\"><i class=\"fa-solid " +
            "fa-spinner fa-spin fa-2x text-muted\"></i></div>";
        try {
            const [sData, gData] = await Promise.all([
                fetchAPI("/get-available-software", {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ devices: Object.values(managedDeviceCache) })
                }),
                fetchAPI("/get-software-groups")
            ]);
            allSoftwareCache = sData.available_software;
            const groups = gData.groups;
            const allGroupedIds = new Set();
            Object.values(groups).forEach(idList => {
                idList.forEach(id => allGroupedIds.add(id));
            });

            let tabNav = "<ul class=\"nav nav-tabs\" id=\"st\" role=\"tablist\">";
            let tabContent = "<div class=\"tab-content\" id=\"sc\">";
            let active = "active";

            Object.keys(groups).forEach(gName => {
                const tId = "tab-" + gName.replace(/\s+/g, "-");
                const bId = tId + "-btn";
                tabNav += "<li class=\"nav-item\"><button class=\"nav-link " + active +
                    "\" id=\"" + bId + "\" data-bs-toggle" + "=\"tab\" " +
                    "data-bs-target" + "=\"#" + tId + "\" type=\"button\">" +
                    gName + "</button></li>";
                tabContent += "<div class=\"tab-pane fade show " + active +
                    " p-3\" id=\"" + tId + "\" role=\"tabpanel\">";
                groups[gName].forEach(id => {
                    const comp = allSoftwareCache.find(comp => comp.id === id);
                    if (comp) tabContent += createComponentInput(comp, gName, "radio");
                });
                tabContent += "</div>";
                active = "";
            });

            tabNav += "<li class=\"nav-item\"><button class=\"nav-link\" id=\"" +
                "tab-stnd-btn\" data-bs-toggle" + "=\"tab\" data-bs-target" +
                "=\"#tab-stnd\" type=\"button\">Standalone</button></li></ul>";
            tabContent += "<div class=\"tab-pane fade p-3\" id=\"tab-stnd\" " +
                "role=\"tabpanel\">";
            allSoftwareCache.forEach(c => {
                if (!allGroupedIds.has(c.id)) {
                    tabContent += createComponentInput(c, "stnd", "checkbox");
                }
            });
            tabContent += "</div></div>";

            wizardBody.innerHTML = "<div class=\"text-start\">" + tabNav + tabContent +
                "<div class=\"d-grid col-8 mx-auto my-4\"><button id=\"step4-btn\" " +
                "class=\"btn btn-primary btn-lg\">Configure Services</button></div></div>";
            document.getElementById("step4-btn").onclick = renderStep4_ConfigureServices;
        } catch (err) { wizardBody.innerHTML = "Error loading software list."; }
    };

    const renderStep4_ConfigureServices = async () => {
        const sel = document.querySelectorAll("#sc input:checked");
        selectedComponentsCache = Array.from(sel).map(i => i.value);
        wizardHeader.innerHTML = "<strong>Step 4 of 5: Configure Services</strong>";
        try {
            const data = await fetchAPI("/get-required-variables", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ selected_components: selectedComponentsCache })
            });
            const comps = data.components;

            // BUILD THE CONFIGURATION GRID PARTS
            let nav = "<div class=\"col-md-3\"><div class=\"nav flex-column nav-pills\" " +
                "role=\"tablist\">";
            let cont = "<div class=\"col-md-9\"><div class=\"tab-content\">";

            selectedComponentsCache.forEach((id, idx) => {
                const fullC = allSoftwareCache.find(c => c.id === id);
                if (!fullC) return;
                const active = idx === 0 ? "active" : "";
                const bId = "t-" + id;
                const tId = "tp-" + id;
                nav += "<button class=\"nav-link " + active + "\" data-bs-toggle=\"" +
                    "pill\" data-bs-target" + "=\"#" + tId + "\" id=\"" + bId + "\">" +
                    fullC.name + "</button>";
                cont += "<div class=\"tab-pane fade show " + active + "\" id=\"" +
                    tId + "\" role=\"tabpanel\">";
                (comps[id]?.variables || []).forEach(v => {
                    cont += "<div class=\"mb-3\"><label>" + (v.label || v.id) +
                        "</label><input type=\"text\" class=\"form-control\" " +
                        "name=\"" + v.id + "\" value=\"" + (v.default || "") +
                        "\"></div>";
                });
                const clId = "cl-" + id;
                cont += "<div class=\"form-check\"><input class=\"form-check-input " +
                    "clean-install-checkbox\" type=\"checkbox\" id=\"" + clId +
                    "\" data-comp-id=\"" + id + "\"><label for" + "=\"" + clId +
                    "\">Clean Install</label></div>";
                if (fullC.post_install_restart_option) {
                    const rsId = "rs-" + id;
                    cont += "<div class=\"form-check\"><input class=\"" +
                        "form-check-input restart-checkbox\" type=\"checkbox\" " +
                        "id=\"" + rsId + "\" data-comp-id=\"" + id + "\"><label " +
                        "for" + "=\"" + rsId + "\">Restart container</label></div>";
                }
                cont += "</div>";
            });

            // ASSEMBLE STEP 4: Place the Review button rows BELOW the row of columns.
            const gridHTML = "<div class=\"row\">" + nav + "</div>" + cont +
                "</div></div></div>";
            const buttonArea = "<div class=\"d-grid col-8 mx-auto my-4 mt-5\">" +
                "<button id=\"review-btn\" class=\"btn btn-primary btn-lg\">" +
                "Review Selections</button></div>";

            wizardBody.innerHTML = "<div class=\"text-start\">" + gridHTML +
                "<div class=\"row\">"  +
                buttonArea + "</div></div>";
            document.getElementById("review-btn").onclick = handleReviewSelection;
        } catch (err) { wizardBody.innerHTML = "Error loading configuration."; }
    };

    const handleReviewSelection = async () => {
        const btn = document.getElementById("review-btn");
        setButtonState(btn, true);
        finalVariablesCache = {};
        document.querySelectorAll(".tab-pane input[name]").forEach(i => {
            const el = /** @type {HTMLInputElement} */ (i);
            finalVariablesCache[el.name] = el.value;
        });

        // HARVEST DATA: Explicitly collect port and volume values for analysis
        const payload = selectedComponentsCache.map(id => {
            const d = allSoftwareCache.find(c => c.id === id);
            const compObj = { name: d?.name || id, id: id, ports: [], volumes: [] };
            const panel = document.getElementById("tp-" + id);
            if (panel) {
                panel.querySelectorAll("input[name]").forEach(input => {
                    const el = /** @type {HTMLInputElement} */ (input);
                    if (el.name.toUpperCase().endsWith("_PORT")) {
                        compObj.ports.push(el.value + ":" + el.value + "/tcp");
                    }
                    if (el.name.toUpperCase().endsWith("_VOLUME_PATH")) {
                        compObj.volumes.push(el.value);
                    }
                });
            }
            return compObj;
        });

        componentsToCleanCache = Array.from(document.querySelectorAll(
            ".clean-install-checkbox:checked")).map(cb => {
            const el = /** @type {HTMLElement} */ (cb);
            return el.dataset.compId;
        });
        componentsToRestartCache = Array.from(document.querySelectorAll(
            ".restart-checkbox:checked")).map(cb => {
            const el = /** @type {HTMLElement} */ (cb);
            return el.dataset.compId;
        });

        try {
            const res = await fetchAPI("/api/v1/system/analyze", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    devices: Object.values(managedDeviceCache),
                    components: payload,
                    is_reinstallation: componentsToCleanCache.length > 0
                })
            });
            analysisResultsCache = res;
            let items = "";
            let blocked = false;
            (res.external_conflicts?.ports || []).forEach(p => {
                const isUpdate = p.conflict_type === "EXPECTED_REINSTALLATION";
                if (!isUpdate) blocked = true;
                const cName = isUpdate ? "text-info" : "text-danger";
                const label = isUpdate ? "Safe Update" : "Conflict";
                items += "<li class=\"list-group-item " + cName + "\">Port " +
                    p.port + " (" + label + ")</li>";
            });
            if (!items) items = "<li class=\"list-group-item text-success\">" +
                "No conflicts found.</li>";

            document.getElementById("am")?.remove();
            const modal = "<div class=\"modal fade\" id=\"am\"><div class=\"" +
                "modal-dialog modal-dialog-centered\"><div class=\"modal-content\">" +
                "<div class=\"modal-header\"><h6>Analysis Result</h6></div><div " +
                "class=\"modal-body\"><ul>" + items + "</ul></div><div class=\"" +
                "modal-footer\"><button class=\"btn btn-secondary\" " +
                "data-bs-dismiss=\"modal\">Back</button><button class=\"btn " +
                "btn-primary\" id=\"modal-p-btn\" " + (blocked ? "disabled" : "") +
                ">Proceed</button></div></div></div></div>";
            document.body.insertAdjacentHTML("beforeend", modal);
            const m = new bootstrap.Modal(document.getElementById("am"));
            document.getElementById("modal-p-btn").onclick = () => {
                m.hide();
                renderStep5_Confirmation();
            };
            m.show();
        } catch (err) { updateWizardFooter("Analysis failed.", "danger"); }
        finally { setButtonState(btn, false); }
    };

    const renderStep5_Confirmation = () => {
        wizardHeader.innerHTML = "<strong>Step 5 of 5: Confirmation</strong>";
        const dH = Object.values(managedDeviceCache).map(d => "<li>" +
            d.hostname + " (" + d.ip + ")</li>").join("");
        wizardBody.innerHTML = "<div class=\"text-start\"><h6>Devices</h6><ul>" +
            dH + "</ul><div class=\"d-grid col-8 mx-auto my-4\"><button id=\"" +
            "gen-btn\" class=\"btn btn-success btn-lg\">Generate & Deploy" +
            "</button></div></div>";
        document.getElementById("gen-btn").onclick = handleInstallation;
    };

    const handleInstallation = async () => {
        const btn = document.getElementById("gen-btn");
        setButtonState(btn, true);
        try {
            const res = await fetchAPI("/start-installation", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    selected_components: selectedComponentsCache,
                    devices: Object.values(managedDeviceCache),
                    env_vars: finalVariablesCache
                })
            });
            wizardHeader.innerHTML = "<strong>Deployment</strong>";
            wizardBody.innerHTML = "<div class=\"text-center\"><button id=\"" +
                "dp-btn\" class=\"btn btn-primary mb-4\">Deploy</button><div id=\"" +
                "sm-box\"></div><div id=\"lb\" style=\"display: none;\">" +
                "<div class=\"card bg-dark text-white p-3 text-start\" style=\"" +
                "max-height: 300px; overflow-y: auto;\"><pre id=\"lo\" " +
                "style=\"white-space: pre-wrap;\"></pre></div></div></div>";
            document.getElementById("dp-btn").onclick = () =>
                handleDeployment(res.output_path);
        } catch (err) { wizardBody.innerHTML = "Failed to generate files."; }
    };

    const showServicesSummary = async (taskId) => {
        try {
            const res = await fetchAPI("/task-status/" + taskId);
            const links = res.service_links || [];
            if (links.length > 0) {
                const html = links.map(l => "<li><a href=\"" + l.url +
                    "\" target=\"_blank\">" + l.name + "</a>: " + l.url + "</li>").join("");
                const smBox = document.getElementById("sm-box");
                smBox.innerHTML = "<div class=\"card mb-4\"><div class=\"card-body\">" +
                    "<ul>" + html + "</ul></div></div>";
            }
        } catch (err) { console.error(err); }
    };

    const handleDeployment = async (path) => {
        const btn = document.getElementById("dp-btn");
        const logBox = document.getElementById("lb");
        const logOut = document.getElementById("lo");
        setButtonState(btn, true);
        logBox.style.display = "block";
        try {
            const selData = selectedComponentsCache
                .map(id => allSoftwareCache.find(c => c.id === id)).filter(Boolean);
            const res = await fetchAPI("/deploy-configuration", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    output_path: path, devices: Object.values(managedDeviceCache),
                    components_to_clean: componentsToCleanCache,
                    components_to_restart: componentsToRestartCache,
                    analysis_results: analysisResultsCache,
                    selected_components_data: selData,
                    global_vars: finalVariablesCache
                })
            });
            const source = new EventSource("/stream-deployment/" + res.task_id);
            source.onmessage = e => {
                logOut.textContent += e.data + "\n";
                logOut.parentElement.scrollTop = logOut.parentElement.scrollHeight;
            };
            source.onerror = () => {
                source.close();
                setButtonState(btn, false, { text: "Complete" });
                showServicesSummary(res.task_id);
            };
        } catch (err) { setButtonState(btn, false); }
    };

    const scanBtn = document.getElementById("begin-scan-btn");
    if (scanBtn) scanBtn.onclick = async () => {
        setButtonState(scanBtn, true);
        try {
            const res = await fetchAPI("/scan-pis", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ subnet: null })
            });
            renderStep2_ConfigureDevices(res);
        } catch (err) { updateWizardFooter("Scan failed.", "danger"); }
        finally { setButtonState(scanBtn, false); }
    };
});
