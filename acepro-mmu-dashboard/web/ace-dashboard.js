// ValgACE Dashboard JavaScript
const { createApp } = Vue;

// ===== Extensive material list (provided earlier, de‑duplicated) =====
const BUILT_IN_MATERIALS = [
  "ABS", "ABS-CF", "ABS-GF", "ASA", "ASA-CF", "ASA-GF", "ASA-AERO",
  "BVOH", "CoPE", "EVA", "FLEX", "HIPS", "PA", "PA-CF", "PA6", "PA6-CF",
  "PA6-GF", "PA11", "PA11-CF", "PA11-GF", "PA12", "PA12-CF", "PA12-GF",
  "PAHT", "PAHT-CF", "PAHT-GF", "PC", "PC-ABS", "PC-CF", "PC-PBT", "PCL",
  "PCTG", "PE", "PE-CF", "PE-GF", "PEI-1010", "PEI-1010-CF", "PEI-1010-GF",
  "PEI-9085", "PEI-9085-CF", "PEI-9085-GF", "PEEK", "PEEK-CF", "PEEK-GF",
  "PEKK", "PEKK-CF", "PES", "PET", "PET-CF", "PET-GF", "PETG", "PETG-CF",
  "PETG-GF", "PHA", "PI", "PLA", "PLA-AERO", "PLA-CF", "POM", "PP", "PP-CF",
  "PP-GF", "PPA-CF", "PPA-GF", "PPS", "PPS-CF", "PPSU", "PSU", "PVA", "PVB",
  "PVDF", "SBS", "TPI", "TPU"
];
const UNIQUE_MATERIALS = [...new Set(BUILT_IN_MATERIALS)];

createApp({
    data() {
        return {
            currentLanguage: 'en',
            translations: {
                en: {
                    header: {
                        title: 'ACE Control Panel',
                        connectionLabel: 'Status',
                        connected: 'Connected',
                        disconnected: 'Disconnected',
                        instance: 'ACE Instance:',
                        instanceLabel: 'ACE {index}'
                    },
                    cards: {
                        deviceStatus: 'Device Status',
                        dryer: 'Dryer Control',
                        slots: 'Filament Slots',
                        quickActions: 'Quick Actions'
                    },
                    deviceInfo: {
                        model: 'Model',
                        firmware: 'Firmware',
                        bootFirmware: 'Boot Firmware',
                        status: 'Status',
                        temp: 'Temperature',
                        fan: 'Fan Speed',
                        usb: 'USB',
                        rfid: 'RFID',
                        rfidOn: 'Enabled',
                        rfidOff: 'Disabled'
                    },
                    dryer: {
                        status: 'Status',
                        targetTemp: 'Target Temperature',
                        duration: 'Set Duration',
                        remainingTime: 'Remaining Time',
                        currentTemperature: 'Current Temperature',
                        inputs: {
                            temp: 'Temperature (°C):',
                            duration: 'Duration (e.g., 4h15m):'
                        },
                        buttons: {
                            start: 'Start Drying',
                            stop: 'Stop Drying'
                        }
                    },
                    slots: {
                        slot: 'Slot',
                        status: 'Status',
                        type: 'Material',
                        preset: 'Preset Name',
                        temp: 'Temp',
                        sku: 'SKU',
                        rfid: 'RFID'
                    },
                    quickActions: {
                        unload: 'Save Inventory',
                        stopAssist: 'Stop All Assist',
                        refresh: 'Refresh Status'
                    },
                    buttons: {
                        load: 'Load',
                        unload: 'Unload',
                        assistOn: 'Assist ON',
                        assistOff: 'Assist OFF'
                    },
                    dialogs: {
                        feedTitle: 'Feed Filament - Slot {slot}',
                        retractTitle: 'Retract Filament - Slot {slot}',
                        length: 'Length (mm):',
                        speed: 'Speed (mm/s):',
                        execute: 'Execute',
                        cancel: 'Cancel'
                    },
                    notifications: {
                        websocketConnected: 'WebSocket connected',
                        websocketDisconnected: 'WebSocket disconnected',
                        apiError: 'API error: {error}',
                        loadError: 'Status load error: {error}',
                        commandSuccess: 'Command {command} executed successfully',
                        commandSent: 'Command {command} sent',
                        commandError: 'Error: {error}',
                        commandErrorGeneric: 'Command execution error',
                        executeError: 'Command execution error: {error}',
                        feedAssistOn: 'Feed assist enabled for slot {index}',
                        feedAssistOff: 'Feed assist disabled for slot {index}',
                        feedAssistAllOff: 'Feed assist disabled for all slots',
                        feedAssistAllOffError: 'Failed to disable feed assist',
                        refreshStatus: 'Status refreshed',
                        dryingComplete: 'Drying cycle completed!',
                        validation: {
                            tempRange: 'Temperature must be between 20 and 65°C',
                            durationMin: 'Duration must be at least 1 minute',
                            feedLength: 'Length must be at least 1 mm',
                            retractLength: 'Length must be at least 1 mm'
                        }
                    },
                    statusMap: {
                        ready: 'Ready',
                        busy: 'Busy',
                        unknown: 'Unknown',
                        disconnected: 'Disconnected'
                    },
                    dryerStatusMap: {
                        drying: 'Drying',
                        stop: 'Stopped'
                    },
                    connectionStateMap: {
                        connected: 'Connected',
                        reconnecting: 'Reconnecting',
                        connecting: 'Connecting',
                        initializing: 'Initializing',
                        disabled: 'Disabled',
                        disconnected: 'Disconnected',
                        unknown: 'Unknown'
                    },
                    slotStatusMap: {
                        ready: 'Ready',
                        empty: 'Empty',
                        busy: 'Busy',
                        unknown: 'Unknown'
                    },
                    rfidStatusMap: {
                        0: 'Not found',
                        1: 'Error',
                        2: 'Identified',
                        3: 'Identifying...'
                    },
                    common: {
                        unknown: 'Unknown'
                    },
                    time: {
                        hours: 'h',
                        minutes: 'min',
                        minutesShort: 'm',
                        secondsShort: 's'
                    }
                }
            },
            // Connection
            wsConnected: false,
            ws: null,
            apiBase: ACE_DASHBOARD_CONFIG?.apiBase || window.location.origin,

            // Device Status
            deviceStatus: {
                status: 'unknown',
                connection_state: 'unknown',
                model: 'Anycubic Color Engine Pro',
                firmware: 'N/A',
                boot_firmware: 'N/A',
                temp: 0,
                fan_speed: 0,
                enable_rfid: 0,
                usb_port: '',
                usb_path: ''
            },

            // Dryer
            dryerStatus: {
                status: 'stop',
                target_temp: 0,
                duration: 0,
                remain_time: 0
            },
            dryingTemp: ACE_DASHBOARD_CONFIG?.defaults?.dryingTemp || 50,
            dryingDuration: ACE_DASHBOARD_CONFIG?.defaults?.dryingDuration || 240,
            dryingHours: 4,
            dryingMinutes: 0,
            localRemainingMinutes: null,
            dryerTimerInterval: null,

            // Slots
            slots: [],
            currentTool: -1,
            feedAssistSlot: -1,
            instanceOptions: [],
            selectedInstance: 0,
            selectedDryerInstance: 0,
            instancesPanels: [],
            colorPresets: [
                { name: 'Red', hex: '#ff0000' },
                { name: 'Green', hex: '#00ff00' },
                { name: 'Blue', hex: '#0000ff' },
                { name: 'Orange', hex: '#ff9900' },
                { name: 'Yellow', hex: '#ffff00' },
                { name: 'Magenta', hex: '#ff00ff' },
                { name: 'Cyan', hex: '#00ffff' },
                { name: 'White', hex: '#ffffff' },
                { name: 'Gray', hex: '#808080' },
                { name: 'Black', hex: '#000000' }
            ],
            materialOptions: UNIQUE_MATERIALS.reduce((obj, mat) => {
				let temp = 200;
				if (mat === 'PLA') temp = 200;
				else if (mat === 'PLA-CF') temp = 205;
				else if (mat === 'PLA-AERO') temp = 200;
				else if (mat === 'PETG') temp = 235;
				else if (mat === 'PETG-CF') temp = 240;
				else if (mat === 'PETG-GF') temp = 240;
				else if (mat === 'ABS') temp = 240;
				else if (mat === 'ABS-CF') temp = 245;
				else if (mat === 'ABS-GF') temp = 245;
				else if (mat === 'ASA') temp = 245;
				else if (mat === 'ASA-CF') temp = 250;
				else if (mat === 'ASA-GF') temp = 250;
				else if (mat === 'ASA-AERO') temp = 245;
				else if (mat === 'TPU') temp = 210;
				else if (mat === 'PC') temp = 260;
				else if (mat === 'PC-CF') temp = 265;
				else if (mat === 'PC-ABS') temp = 250;
				else if (mat === 'PC-PBT') temp = 255;
				else if (mat === 'PA') temp = 260;
				else if (mat === 'PA-CF') temp = 265;
				else if (mat === 'PA6') temp = 260;
				else if (mat === 'PA6-CF') temp = 265;
				else if (mat === 'PA6-GF') temp = 265;
				else if (mat === 'PA11') temp = 250;
				else if (mat === 'PA11-CF') temp = 255;
				else if (mat === 'PA11-GF') temp = 255;
				else if (mat === 'PA12') temp = 250;
				else if (mat === 'PA12-CF') temp = 255;
				else if (mat === 'PA12-GF') temp = 255;
				else if (mat === 'PAHT') temp = 270;
				else if (mat === 'PAHT-CF') temp = 275;
				else if (mat === 'PAHT-GF') temp = 275;
				else if (mat === 'PEEK') temp = 380;
				else if (mat === 'PEEK-CF') temp = 390;
				else if (mat === 'PEEK-GF') temp = 390;
				else if (mat === 'PEKK') temp = 370;
				else if (mat === 'PEKK-CF') temp = 380;
				else if (mat === 'PEI-1010') temp = 370;
				else if (mat === 'PEI-1010-CF') temp = 375;
				else if (mat === 'PEI-1010-GF') temp = 375;
				else if (mat === 'PEI-9085') temp = 360;
				else if (mat === 'PEI-9085-CF') temp = 365;
				else if (mat === 'PEI-9085-GF') temp = 365;
				else if (mat === 'PPS') temp = 320;
				else if (mat === 'PPS-CF') temp = 325;
				else if (mat === 'PPSU') temp = 360;
				else if (mat === 'PSU') temp = 350;
				else if (mat === 'PES') temp = 340;
				else if (mat === 'POM') temp = 220;
				else if (mat === 'PP') temp = 230;
				else if (mat === 'PP-CF') temp = 235;
				else if (mat === 'PP-GF') temp = 235;
				else if (mat === 'PPA-CF') temp = 280;
				else if (mat === 'PPA-GF') temp = 280;
				else if (mat === 'HIPS') temp = 230;
				else if (mat === 'PVA') temp = 210;
				else if (mat === 'PVB') temp = 190;
				else if (mat === 'BVOH') temp = 200;
				else if (mat === 'PCL') temp = 90;
				else if (mat === 'PCTG') temp = 240;
				else if (mat === 'PET') temp = 240;
				else if (mat === 'PET-CF') temp = 245;
				else if (mat === 'PET-GF') temp = 245;
				else if (mat === 'PE') temp = 200;
				else if (mat === 'PE-CF') temp = 205;
				else if (mat === 'PE-GF') temp = 205;
				else if (mat === 'CoPE') temp = 200;
				else if (mat === 'EVA') temp = 190;
				else if (mat === 'FLEX') temp = 210;
				else if (mat === 'SBS') temp = 210;
				else if (mat === 'TPI') temp = 280;
				else if (mat === 'PVDF') temp = 240;
				else if (mat === 'PHA') temp = 200;
				else if (mat === 'PI') temp = 360;
                else temp = 0;
                obj[mat] = temp;
                return obj;
            }, {}),
            rfidSyncEnabled: false,
            editingHex: {},

            // Modals
            showFeedModal: false,
            showRetractModal: false,
            feedSlot: 0,
            feedLength: ACE_DASHBOARD_CONFIG?.defaults?.feedLength || 50,
            feedSpeed: ACE_DASHBOARD_CONFIG?.defaults?.feedSpeed || 25,
            retractSlot: 0,
            retractLength: ACE_DASHBOARD_CONFIG?.defaults?.retractLength || 50,
            retractSpeed: ACE_DASHBOARD_CONFIG?.defaults?.retractSpeed || 25,
            showColorPickerModal: false,
            colorPickerTarget: null,
            modalMaterial: '',
            modalTemp: 0,
            modalColorHex: '#ffffff',
            modalPresetName: '',

            presetFeedLength: ACE_DASHBOARD_CONFIG?.defaults?.presetFeedLength || 50,
            presetRetractLength: ACE_DASHBOARD_CONFIG?.defaults?.presetRetractLength || 50,

            notification: {
                show: false,
                message: '',
                type: 'info'
            },

            // Preset library
            showPresetLibrary: false,
            presets: []
        };
    },

    computed: {
        dryerProgress() {
            const remaining = this.getRemainingMinutes();
            const duration = this.dryerStatus.duration;
            if (duration <= 0 || remaining <= 0) return 0;
            const elapsed = duration - remaining;
            const percent = (elapsed / duration) * 100;
            return Math.min(100, Math.max(0, percent));
        },
        formattedRemaining() {
            const mins = this.getRemainingMinutes();
            if (!mins || mins <= 0) return '00:00';
            const hours = Math.floor(mins / 60);
            const minutes = Math.floor(mins % 60);
            const seconds = Math.floor((mins - Math.floor(mins)) * 60);
            if (hours > 0) {
                return `${hours.toString().padStart(2,'0')}:${minutes.toString().padStart(2,'0')}:${seconds.toString().padStart(2,'0')}`;
            }
            return `${minutes.toString().padStart(2,'0')}:${seconds.toString().padStart(2,'0')}`;
        }
    },

    mounted() {
        this.loadPresetsFromPrinter();
        this.connectWebSocket();
        this.loadAllStatus();
        this.updateDocumentTitle();
        const refreshInterval = ACE_DASHBOARD_CONFIG?.autoRefreshInterval || 5000;
        setInterval(() => {
            if (this.wsConnected) this.loadAllStatus();
        }, refreshInterval);
    },

    beforeDestroy() {
        this.stopDryerTimer();
    },

    methods: {
        t(path, params = {}) {
            const keys = path.split('.');
            let value = this.translations[this.currentLanguage];
            for (const key of keys) {
                if (value && Object.prototype.hasOwnProperty.call(value, key)) {
                    value = value[key];
                } else {
                    return undefined;
                }
            }
            if (typeof value === 'string') {
                return value.replace(/\{(\w+)\}/g, (match, token) => {
                    return Object.prototype.hasOwnProperty.call(params, token) ? params[token] : match;
                });
            }
            return undefined;
        },

        // ------------------- Helper UI methods -------------------
        isSlotHexEditing(instIndex, slotIndex) {
            const key = `${instIndex}-${slotIndex}`;
            return !!this.editingHex[key];
        },

        getPreviousHex(prevPanel, slotIndex) {
            if (!prevPanel || !Array.isArray(prevPanel.slots)) return null;
            const found = prevPanel.slots.find(s => s.index === slotIndex);
            return found ? found.hex : null;
        },

        startHexEdit(instIndex, slotIndex) {
            const key = `${instIndex}-${slotIndex}`;
            const next = { ...this.editingHex };
            next[key] = true;
            this.editingHex = next;
        },

        commitSlotHex(slot, instanceIndex) {
            if (!slot) return;
            const val = slot.hex || '';
            const hex = (typeof val === 'string' && /^#?[0-9a-fA-F]{6}$/.test(val.trim())) ? (val.trim().startsWith('#') ? val.trim() : `#${val.trim()}`) : null;
            if (!hex) {
                this.showNotification('Invalid hex color', 'error');
                return;
            }
            const normalized = hex.trim().startsWith('#') ? hex.trim() : `#${hex.trim()}`;
            slot.hex = normalized;
            this.setSlotColor(slot.index, instanceIndex, normalized, slot.tool, slot.material || slot.type || '', slot.temp, slot.custom_name);
            const key = `${instanceIndex}-${slot.index}`;
            const next = { ...this.editingHex };
            delete next[key];
            this.editingHex = next;
        },

        getInstanceFeedAssistSlot(instanceIndex) {
            const panel = this.instancesPanels.find(p => p.index === instanceIndex);
            return (panel && typeof panel.feedAssistSlot === 'number') ? panel.feedAssistSlot : -1;
        },

        setInstanceFeedAssistSlot(instanceIndex, slotIndex) {
            this.instancesPanels = this.instancesPanels.map(panel => {
                if (panel.index !== instanceIndex) return panel;
                return { ...panel, feedAssistSlot: slotIndex };
            });
            if (instanceIndex === this.selectedInstance) {
                this.feedAssistSlot = slotIndex;
            }
        },

        isSlotLocked(inst, slot) {
            const instIndex = typeof inst === 'number' ? inst : inst?.index;
            const panel = this.instancesPanels.find(p => p.index === instIndex);
            const syncEnabled = panel ? panel.rfidSyncEnabled : this.rfidSyncEnabled;
            return !!(syncEnabled && slot && slot.rfid === 2);
        },

        updateDocumentTitle() {
            document.title = this.t('header.title');
        },

        // ------------------- Dryer timer -------------------
        getRemainingMinutes() {
            return this.localRemainingMinutes !== null ? this.localRemainingMinutes : this.dryerStatus.remain_time;
        },

        startDryerTimer(initialMinutes) {
            this.stopDryerTimer();
            if (initialMinutes === undefined || initialMinutes === null) {
                initialMinutes = this.dryerStatus.remain_time;
            }
            if (initialMinutes <= 0) {
                this.localRemainingMinutes = 0;
                return;
            }
            this.localRemainingMinutes = initialMinutes;
            this.dryerTimerInterval = setInterval(() => {
                if (this.localRemainingMinutes > 0) {
                    this.localRemainingMinutes -= 1/60;
                    if (this.localRemainingMinutes < 0) this.localRemainingMinutes = 0;
                }
                if (this.localRemainingMinutes <= 0 && this.dryerStatus.status === 'drying') {
                    this.stopDryerTimer();
                    this.showNotification(this.t('notifications.dryingComplete'), 'success');
                }
            }, 1000);
        },

        stopDryerTimer() {
            if (this.dryerTimerInterval) {
                clearInterval(this.dryerTimerInterval);
                this.dryerTimerInterval = null;
            }
            this.localRemainingMinutes = null;
        },

        syncRemainingTimeWithAPI(apiRemain) {
            if (!this.dryerTimerInterval) {
                if (this.dryerStatus.status === 'drying') {
                    this.startDryerTimer(apiRemain);
                }
                return;
            }
            const diff = Math.abs(this.localRemainingMinutes - apiRemain);
            if (diff > 0.034) {
                this.localRemainingMinutes = apiRemain;
                if (this.localRemainingMinutes <= 0) {
                    this.stopDryerTimer();
                    this.showNotification(this.t('notifications.dryingComplete'), 'success');
                }
            }
        },

        // ------------------- WebSocket -------------------
        connectWebSocket() {
            const wsUrl = getWebSocketUrl();
            this.ws = new WebSocket(wsUrl);
            this.ws.onopen = () => {
                this.wsConnected = true;
                this.showNotification(this.t('notifications.websocketConnected'), 'success');
                this.subscribeToStatus();
                // Immediately fetch status to get latest slot data after connection
                this.loadAllStatus();
            };
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (e) {
                    console.error('Error parsing WebSocket message:', e);
                }
            };
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.wsConnected = false;
            };
            this.ws.onclose = () => {
                this.wsConnected = false;
                this.showNotification(this.t('notifications.websocketDisconnected'), 'error');
                const reconnectTimeout = ACE_DASHBOARD_CONFIG?.wsReconnectTimeout || 3000;
                setTimeout(() => this.connectWebSocket(), reconnectTimeout);
            };
        },

        subscribeToStatus() {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
            this.ws.send(JSON.stringify({
                jsonrpc: "2.0",
                method: "printer.objects.subscribe",
                params: { objects: { "ace": null } },
                id: 5434
            }));
        },

        handleWebSocketMessage(data) {
            if (data.method === "notify_status_update") {
                const aceData = data.params[0]?.ace;
                if (aceData) {
                    if (typeof aceData.instance_index === 'number' && aceData.instance_index !== this.selectedInstance) {
                        return;
                    }
                    this.updateMainStatus(aceData);
                }
            }
        },

        // ------------------- API Calls -------------------
        async loadAllStatus() {
            await Promise.all([
                this.loadStatusForInstance(this.selectedInstance, 'main'),
                this.loadStatusForInstance(this.selectedDryerInstance, 'dryer')
            ]);
        },

        async loadStatusForInstance(instance, target) {
            try {
                const response = await fetch(`${this.apiBase}/server/ace/status?instance=${instance}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const result = await response.json();
                const statusData = result.result || result;
                if (target === 'main') {
                    this.updateMainStatus(statusData);
                } else if (target === 'dryer') {
                    this.updateDryerStatus(statusData);
                }
            } catch (error) {
                console.error(`Error loading status for instance ${instance}:`, error);
                if (target === 'dryer') {
                    this.showNotification(`Failed to load dryer status: ${error.message}`, 'error');
                }
            }
        },

        updateMainStatus(data) {
            if (!data || typeof data !== 'object') {
                console.warn('Invalid main status data:', data);
                return;
            }

            let incomingCurrentTool = null;
            const topLevelCurrent = Number(data.current_index);
            const managerCurrent = Number(data?.ace_manager?.current_index);
            if (Number.isInteger(topLevelCurrent)) {
                incomingCurrentTool = topLevelCurrent;
            } else if (Number.isInteger(managerCurrent)) {
                incomingCurrentTool = managerCurrent;
            }
            if (incomingCurrentTool !== null) {
                this.currentTool = incomingCurrentTool;
            }

            if (typeof data.rfid_sync_enabled === 'boolean') {
                this.rfidSyncEnabled = data.rfid_sync_enabled;
            }

            if (ACE_DASHBOARD_CONFIG?.debug) {
                console.log('Updating main status with data:', data);
            }

            const instances = Array.isArray(data.instances) ? data.instances : [];
            this.instanceOptions = instances
                .map(item => ({ index: typeof item?.index === 'number' ? item.index : 0 }))
                .sort((a, b) => a.index - b.index);
            if (typeof data.instance_index === 'number') {
                if (!Number.isInteger(this.selectedInstance) ||
                    !this.instanceOptions.find(opt => opt.index === this.selectedInstance)) {
                    this.selectedInstance = data.instance_index;
                }
            }

            if (data.status !== undefined) this.deviceStatus.status = data.status;
            if (data.connection_state !== undefined) this.deviceStatus.connection_state = data.connection_state || 'unknown';
            if (data.model !== undefined) this.deviceStatus.model = data.model;
            if (data.firmware !== undefined) this.deviceStatus.firmware = data.firmware;
            if (data.boot_firmware !== undefined) this.deviceStatus.boot_firmware = data.boot_firmware;
            if (data.temp !== undefined) this.deviceStatus.temp = data.temp;
            if (data.fan_speed !== undefined) this.deviceStatus.fan_speed = data.fan_speed;
            if (data.usb_port !== undefined) this.deviceStatus.usb_port = data.usb_port;
            if (data.usb_path !== undefined) this.deviceStatus.usb_path = data.usb_path;
            if (data.enable_rfid !== undefined) this.deviceStatus.enable_rfid = data.enable_rfid;

            const instancesRaw = Array.isArray(data.instances) ? data.instances : [];
            const prevPanels = this.instancesPanels || [];
            if (instancesRaw.length > 0) {
                this.instancesPanels = instancesRaw.map(item => {
                    const slotsArr = Array.isArray(item.slots) ? item.slots : [];
                    const prevPanel = prevPanels.find(p => p.index === item.index);
                    return {
                        index: typeof item.index === 'number' ? item.index : 0,
                        slots: slotsArr.map((slot, idx) => {
                            const existingSlot = prevPanel?.slots?.find(s => s.index === slot.index);
                            let customName = (slot.custom_name && slot.custom_name.trim()) ? slot.custom_name : (existingSlot?.custom_name || '');
                            // If still empty, try localStorage
                            if (!customName) {
                                customName = this._loadPresetFromLocalStorage(item.index, slot.index);
                            }
                            return {
                                index: slot.index !== undefined ? slot.index : -1,
                                tool: slot.tool !== undefined ? slot.tool : null,
                                status: slot.status || 'unknown',
                                type: slot.type || slot.material || '',
                                material: slot.material || slot.type || '',
                                temp: typeof slot.temp === 'number' ? slot.temp : 0,
                                color: Array.isArray(slot.color) ? slot.color : [0, 0, 0],
                                hex: this.isSlotHexEditing(item.index, slot.index)
                                    ? this.getPreviousHex(prevPanel, slot.index) || this.getColorHex(slot.color)
                                    : this.getColorHex(slot.color),
                                sku: slot.sku || '',
                                rfid: slot.rfid !== undefined ? slot.rfid : 0,
                                custom_name: customName,
                                customFeedLength: ACE_DASHBOARD_CONFIG?.defaults?.feedLength || 50,
                                customFeedSpeed: ACE_DASHBOARD_CONFIG?.defaults?.feedSpeed || 25,
                                customRetractLength: ACE_DASHBOARD_CONFIG?.defaults?.retractLength || 50,
                                customRetractSpeed: ACE_DASHBOARD_CONFIG?.defaults?.retractSpeed || 25
                            };
                        }),
                        feedAssistSlot: typeof item.feed_assist_slot === 'number' ? item.feed_assist_slot : -1,
                        rfidSyncEnabled: typeof item.rfid_sync_enabled === 'boolean' ? item.rfid_sync_enabled : this.rfidSyncEnabled
                    };
                });
                const selectedPanel = this.instancesPanels.find(p => p.index === this.selectedInstance) || this.instancesPanels[0];
                if (selectedPanel) {
                    this.slots = selectedPanel.slots;
                    this.feedAssistSlot = selectedPanel.feedAssistSlot ?? -1;
                }
            } else if (data.slots !== undefined) {
                if (Array.isArray(data.slots)) {
                    this.slots = data.slots.map(slot => {
                        const existingSlot = this.slots.find(s => s.index === slot.index);
                        let customName = (slot.custom_name && slot.custom_name.trim()) ? slot.custom_name : (existingSlot?.custom_name || '');
                        if (!customName) {
                            customName = this._loadPresetFromLocalStorage(this.selectedInstance, slot.index);
                        }
                        return {
                            index: slot.index !== undefined ? slot.index : -1,
                            tool: slot.tool !== undefined ? slot.tool : null,
                            status: slot.status || 'unknown',
                            type: slot.type || slot.material || '',
                            material: slot.material || slot.type || '',
                            color: Array.isArray(slot.color) ? slot.color : [0, 0, 0],
                            hex: this.isSlotHexEditing(this.selectedInstance, slot.index)
                                ? (this.slots.find(s => s.index === slot.index)?.hex || this.getColorHex(slot.color))
                                : this.getColorHex(slot.color),
                            temp: typeof slot.temp === 'number' ? slot.temp : 0,
                            sku: slot.sku || '',
                            rfid: slot.rfid !== undefined ? slot.rfid : 0,
                            custom_name: customName,
                            customFeedLength: ACE_DASHBOARD_CONFIG?.defaults?.feedLength || 50,
                            customFeedSpeed: ACE_DASHBOARD_CONFIG?.defaults?.feedSpeed || 25,
                            customRetractLength: ACE_DASHBOARD_CONFIG?.defaults?.retractLength || 50,
                            customRetractSpeed: ACE_DASHBOARD_CONFIG?.defaults?.retractSpeed || 25
                        };
                    });
                } else {
                    console.warn('Slots data is not an array:', data.slots);
                }
                if (data.feed_assist_slot !== undefined) {
                    this.feedAssistSlot = data.feed_assist_slot;
                } else if (data.feed_assist_count !== undefined && data.feed_assist_count > 0) {
                    if (this.feedAssistSlot === -1 && this.currentTool !== -1 && this.currentTool < 4) {
                        this.feedAssistSlot = this.currentTool;
                    }
                } else {
                    this.feedAssistSlot = -1;
                }
            }
        },

        updateDryerStatus(data) {
            const dryer = data.dryer || data.dryer_status;
            const oldStatus = this.dryerStatus.status;
            let newRemain = null;

            if (dryer && typeof dryer === 'object') {
                if (dryer.duration !== undefined) this.dryerStatus.duration = Math.floor(dryer.duration);
                if (dryer.remain_time !== undefined) {
                    let remain = dryer.remain_time;
                    if (remain > 1440) remain /= 60;
                    else if (this.dryerStatus.duration > 0 && remain > this.dryerStatus.duration * 1.5 && remain > 60) remain /= 60;
                    newRemain = remain;
                    this.dryerStatus.remain_time = remain;
                }
                if (dryer.status !== undefined) this.dryerStatus.status = dryer.status;
                if (dryer.target_temp !== undefined) this.dryerStatus.target_temp = dryer.target_temp;
            }
            if (data.dryer_target_temp !== undefined) this.dryerStatus.target_temp = data.dryer_target_temp;

            if (this.dryerStatus.status === 'drying') {
                if (oldStatus !== 'drying') {
                    this.startDryerTimer(newRemain);
                } else {
                    if (newRemain !== null) {
                        this.syncRemainingTimeWithAPI(newRemain);
                    }
                }
            } else {
                this.stopDryerTimer();
            }
        },

        onInstanceChange() {
            this.loadStatusForInstance(this.selectedInstance, 'main');
        },

        onDryerInstanceChange() {
            this.loadStatusForInstance(this.selectedDryerInstance, 'dryer');
        },

        async executeCommand(command, params = {}) {
            try {
                const instance = params.INSTANCE !== undefined ? params.INSTANCE : this.selectedInstance;
                const cmdParams = { ...params, INSTANCE: instance };
                const response = await fetch(`${this.apiBase}/server/ace/command`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command, params: cmdParams })
                });
                const result = await response.json();
                if (result.error) {
                    this.showNotification(this.t('notifications.apiError', { error: result.error }), 'error');
                    return false;
                }
                if (result.result && result.result.success === false) {
                    const errorMsg = result.result.error || result.result.message || this.t('notifications.commandErrorGeneric');
                    this.showNotification(this.t('notifications.commandError', { error: errorMsg }), 'error');
                    return false;
                }
                this.showNotification(this.t('notifications.commandSuccess', { command }), 'success');
                setTimeout(() => this.loadAllStatus(), 1000);
                return true;
            } catch (error) {
                console.error('Error executing command:', error);
                this.showNotification(this.t('notifications.executeError', { error: error.message }), 'error');
                return false;
            }
        },

        async changeToolForInstance(tool, instanceIndex) {
            const success = await this.executeCommand('ACE_CHANGE_TOOL', { TOOL: tool, INSTANCE: instanceIndex });
            if (success && instanceIndex === this.selectedInstance) {
                this.currentTool = tool;
            }
        },

        async unloadFilament(instanceIndex) {
            await this.changeToolForInstance(-1, instanceIndex);
        },

        async stopAssist() {
            let anySuccess = false;
            const instances = this.instanceOptions.length > 0 ? this.instanceOptions : [{ index: this.selectedInstance || 0 }];
            for (const inst of instances) {
                const activeSlot = this.getInstanceFeedAssistSlot(inst.index);
                if (activeSlot !== -1) {
                    const success = await this.disableFeedAssist(activeSlot, inst.index, true);
                    if (success) anySuccess = true;
                    continue;
                }
                for (let index = 0; index < 4; index++) {
                    const success = await this.executeCommand('ACE_DISABLE_FEED_ASSIST', { INDEX: index, INSTANCE: inst.index });
                    if (success) {
                        anySuccess = true;
                        this.setInstanceFeedAssistSlot(inst.index, -1);
                    }
                }
            }
            if (anySuccess) {
                this.instancesPanels = this.instancesPanels.map(panel => ({ ...panel, feedAssistSlot: -1 }));
                this.feedAssistSlot = -1;
                this.showNotification(this.t('notifications.feedAssistAllOff'), 'success');
            } else {
                this.showNotification(this.t('notifications.feedAssistAllOffError'), 'error');
            }
        },

        // ========== ENHANCED SAVE INVENTORY ==========
        async saveInventoryAll() {
            const instances = this.instanceOptions.length > 0 ? this.instanceOptions : [{ index: this.selectedInstance || 0 }];
            let anySlotUpdated = false;
            let allSuccessful = true;

            for (const inst of instances) {
                const panel = this.instancesPanels.find(p => p.index === inst.index);
                if (!panel || !Array.isArray(panel.slots)) continue;

                for (const slot of panel.slots) {
                    if (slot.status === 'empty') continue;
                    if (!slot.material || slot.material.trim() === '') continue;

                    const toolNumber = this.getSlotToolNumber(slot, inst.index);
                    const hex = this.getColorHex(slot.color);
                    const presetName = slot.custom_name || '';

                    const success = await this.setSlotColor(
                        slot.index,
                        inst.index,
                        hex,
                        toolNumber,
                        slot.material,
                        slot.temp,
                        presetName
                    );
                    
                    if (success) {
                        anySlotUpdated = true;
                    } else {
                        allSuccessful = false;
                    }
                    
                    // Small delay to avoid flooding the command queue
                    await new Promise(resolve => setTimeout(resolve, 150));
                }
            }

            let saveSuccess = true;
            for (const inst of instances) {
                const success = await this.executeCommand('ACE_SAVE_INVENTORY', { INSTANCE: inst.index });
                if (!success) saveSuccess = false;
            }

            if (anySlotUpdated && saveSuccess) {
                this.showNotification(this.t('notifications.commandSuccess', { command: 'ACE_SAVE_INVENTORY' }), 'success');
                setTimeout(() => this.loadAllStatus(), 500);
            } else if (anySlotUpdated && !saveSuccess) {
                this.showNotification('Slots updated but inventory save failed', 'error');
            } else if (!anySlotUpdated) {
                this.showNotification('No slots were updated (all empty or no material)', 'info');
            } else {
                this.showNotification(this.t('notifications.commandErrorGeneric'), 'error');
            }
        },

        async toggleFeedAssist(index, instanceIndex) {
            const targetInstance = Number.isInteger(instanceIndex) ? instanceIndex : (this.selectedInstance || 0);
            const activeSlot = this.getInstanceFeedAssistSlot(targetInstance);
            if (activeSlot === index) {
                await this.disableFeedAssist(index, targetInstance);
            } else {
                if (activeSlot !== -1) {
                    await this.disableFeedAssist(activeSlot, targetInstance, true);
                }
                await this.enableFeedAssist(index, targetInstance);
            }
        },

        async enableFeedAssist(index, instanceIndex) {
            const targetInstance = Number.isInteger(instanceIndex) ? instanceIndex : (this.selectedInstance || 0);
            const activeSlot = this.getInstanceFeedAssistSlot(targetInstance);
            if (activeSlot !== -1 && activeSlot !== index) {
                await this.disableFeedAssist(activeSlot, targetInstance, true);
            }
            const success = await this.executeCommand('ACE_ENABLE_FEED_ASSIST', { INDEX: index, INSTANCE: targetInstance });
            if (success) {
                this.setInstanceFeedAssistSlot(targetInstance, index);
                this.showNotification(this.t('notifications.feedAssistOn', { index }), 'success');
            }
            return success;
        },

        async disableFeedAssist(index, instanceIndex, silent = false) {
            const targetInstance = Number.isInteger(instanceIndex) ? instanceIndex : (this.selectedInstance || 0);
            const success = await this.executeCommand('ACE_DISABLE_FEED_ASSIST', { INDEX: index, INSTANCE: targetInstance });
            if (success) {
                this.setInstanceFeedAssistSlot(targetInstance, -1);
                if (!silent) {
                    this.showNotification(this.t('notifications.feedAssistOff', { index }), 'success');
                }
            }
            return success;
        },

        // Dryer actions
        startDryingFromInput() {
            if (this.dryingTemp < 20 || this.dryingTemp > 55) {
                this.showNotification(this.t('notifications.validation.tempRange'), 'error');
                return;
            }
            const totalMinutes = (this.dryingHours * 60) + this.dryingMinutes;
            if (totalMinutes < 1) {
                this.showNotification('Duration must be at least 1 minute', 'error');
                return;
            }
            this.dryingDuration = totalMinutes;
            this.executeCommand('ACE_START_DRYING', {
                TEMP: this.dryingTemp,
                DURATION: totalMinutes,
                INSTANCE: this.selectedDryerInstance
            });
        },

        stopDrying() {
            this.executeCommand('ACE_STOP_DRYING', { INSTANCE: this.selectedDryerInstance });
        },

        // Feed/Retract
        async executeCustomFeed(slot, instanceIndex) {
            if (slot.customFeedLength < 1) {
                this.showNotification('Feed length must be at least 1 mm', 'error');
                return;
            }
            await this.executeCommand('ACE_FEED', {
                INDEX: slot.index,
                LENGTH: slot.customFeedLength,
                SPEED: slot.customFeedSpeed,
                INSTANCE: instanceIndex
            });
        },

        async executeCustomRetract(slot, instanceIndex) {
            if (slot.customRetractLength < 1) {
                this.showNotification('Retract length must be at least 1 mm', 'error');
                return;
            }
            await this.executeCommand('ACE_RETRACT', {
                INDEX: slot.index,
                LENGTH: slot.customRetractLength,
                SPEED: slot.customRetractSpeed,
                INSTANCE: instanceIndex
            });
        },

        showFeedDialog(slot) {
            this.feedSlot = slot;
            this.feedLength = ACE_DASHBOARD_CONFIG?.defaults?.feedLength || 50;
            this.feedSpeed = ACE_DASHBOARD_CONFIG?.defaults?.feedSpeed || 25;
            this.showFeedModal = true;
        },

        closeFeedDialog() {
            this.showFeedModal = false;
        },

        async executeFeed() {
            if (this.feedLength < 1) {
                this.showNotification(this.t('notifications.validation.feedLength'), 'error');
                return;
            }
            const success = await this.executeCommand('ACE_FEED', {
                INDEX: this.feedSlot,
                LENGTH: this.feedLength,
                SPEED: this.feedSpeed
            });
            if (success) this.closeFeedDialog();
        },

        showRetractDialog(slot) {
            this.retractSlot = slot;
            this.retractLength = ACE_DASHBOARD_CONFIG?.defaults?.retractLength || 50;
            this.retractSpeed = ACE_DASHBOARD_CONFIG?.defaults?.retractSpeed || 25;
            this.showRetractModal = true;
        },

        closeRetractDialog() {
            this.showRetractModal = false;
        },

        async executeRetract() {
            if (this.retractLength < 1) {
                this.showNotification(this.t('notifications.validation.retractLength'), 'error');
                return;
            }
            const success = await this.executeCommand('ACE_RETRACT', {
                INDEX: this.retractSlot,
                LENGTH: this.retractLength,
                SPEED: this.retractSpeed
            });
            if (success) this.closeRetractDialog();
        },

        async refreshStatus() {
            await this.loadAllStatus();
            this.showNotification(this.t('notifications.refreshStatus'), 'success');
        },

        // Utility Functions
        getStatusText(status) {
            return this.t(`statusMap.${status}`) || status;
        },

        getConnectionStateText(state) {
            const key = state || 'unknown';
            return this.t(`connectionStateMap.${key}`) || this.t('common.unknown');
        },

        connectionBadgeClass() {
            if (!this.wsConnected) return 'disconnected';
            return this.deviceStatus.connection_state || 'unknown';
        },

        getDryerStatusText(status) {
            return this.t(`dryerStatusMap.${status}`) || status;
        },

        getSlotStatusText(status) {
            return this.t(`slotStatusMap.${status}`) || status;
        },

        getRfidStatusText(rfid) {
            let key;
            if (rfid === true) key = 2;
            else if (rfid === false || rfid === null || rfid === undefined) key = 0;
            else key = rfid;
            const value = this.t(`rfidStatusMap.${key}`);
            return value === undefined ? this.t('common.unknown') : value;
        },

        isRfidIdentified(rfid) {
            if (rfid === true) return true;
            if (rfid === false || rfid === null || rfid === undefined) return false;
            if (typeof rfid === 'number') return rfid === 2;
            const str = String(rfid).toLowerCase();
            return str === '2' || str === 'identified';
        },

        formatUsbPath(port, usbPath) {
            if (port && usbPath) return `${port} (${usbPath})`;
            if (port) return port;
            if (usbPath) return usbPath;
            return this.t('common.unknown');
        },

        getColorHex(color) {
            if (!color || !Array.isArray(color) || color.length < 3) return '#000000';
            const r = Math.max(0, Math.min(255, color[0])).toString(16).padStart(2, '0');
            const g = Math.max(0, Math.min(255, color[1])).toString(16).padStart(2, '0');
            const b = Math.max(0, Math.min(255, color[2])).toString(16).padStart(2, '0');
            return `#${r}${g}${b}`;
        },

        rgbToHex(rgb) {
            if (!Array.isArray(rgb) || rgb.length < 3) return '#000000';
            const [r, g, b] = rgb.map(v => Math.max(0, Math.min(255, Number(v) || 0)));
            return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('');
        },

        hexToRgb(hex) {
            if (typeof hex !== 'string') return null;
            const m = hex.trim().match(/^#?([0-9a-fA-F]{6})$/);
            if (!m) return null;
            const intVal = parseInt(m[1], 16);
            return [(intVal >> 16) & 255, (intVal >> 8) & 255, intVal & 255];
        },

        // Preset library methods
        async loadPresetsFromPrinter() {
            try {
                const response = await fetch(`${this.apiBase}/server/files/config/ace_orca_presets.json`);
                if (response.ok) {
                    const data = await response.json();
                    this.presets = data;
                } else {
                    this.presets = [];
                }
            } catch (error) {
                console.warn('Failed to load presets from printer:', error);
                this.presets = [];
            }
        },

        async savePresetsToPrinter() {
            const json = JSON.stringify(this.presets, null, 2);
            const blob = new Blob([json], { type: 'application/json' });
            const formData = new FormData();
            formData.append('file', blob, 'ace_orca_presets.json');
            formData.append('root', 'config');
            try {
                const response = await fetch(`${this.apiBase}/server/files/upload`, {
                    method: 'POST',
                    body: formData
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                this.showNotification('Presets saved to printer', 'success');
            } catch (error) {
                console.error('Failed to save presets:', error);
                this.showNotification('Failed to save presets', 'error');
            }
        },

        importOrcaPresets() {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.json';
            input.multiple = true;
            input.onchange = async (e) => {
                const files = Array.from(e.target.files);
                let added = 0;
                for (const file of files) {
                    try {
                        const text = await file.text();
                        const data = JSON.parse(text);
                        let name = data.filament_settings_id || data.name || file.name.replace(/\.json$/, '');
                        if (Array.isArray(name)) name = name[0];
                        let material = data.filament_type || '';
                        if (Array.isArray(material)) material = material[0];
                        let temp = data.nozzle_temperature || data.temperature || 200;
                        if (Array.isArray(temp)) temp = temp[0];
                        const preset = {
                            name: name.trim(),
                            material: material.trim() || 'Unknown',
                            temp: Number(temp)
                        };
                        const existing = this.presets.find(p => p.name === preset.name);
                        if (!existing) {
                            this.presets.push(preset);
                            added++;
                        }
                    } catch (err) {
                        console.warn('Error parsing file', file.name, err);
                    }
                }
                if (added) {
                    await this.savePresetsToPrinter();
                    this.showNotification(`Imported ${added} new presets.`, 'success');
                } else {
                    this.showNotification('No new presets added.', 'info');
                }
            };
            input.click();
        },

        deletePreset(index) {
            this.presets.splice(index, 1);
            this.savePresetsToPrinter();
            this.showNotification('Preset deleted', 'success');
        },

        clearAllPresets() {
            if (confirm('Delete all imported presets?')) {
                this.presets = [];
                this.savePresetsToPrinter();
                this.showNotification('All presets cleared', 'success');
            }
        },

        // Colour picker modal modifications
        openColorPickerModal(slot, instanceIndex) {
            this.colorPickerTarget = { slot: { ...slot }, instanceIndex };
            this.modalMaterial = slot.material || slot.type || '';
            this.modalTemp = slot.temp || 0;
            this.modalColorHex = this.getColorHex(slot.color);
            this.modalPresetName = slot.custom_name || '';
            this.showColorPickerModal = true;
        },

        closeColorPickerModal() {
            this.showColorPickerModal = false;
            this.colorPickerTarget = null;
        },

        onModalMaterialChange() {
            const builtInTemp = this.materialOptions[this.modalMaterial];
            if (builtInTemp !== undefined) {
                this.modalTemp = builtInTemp;
            }
        },

        onModalPresetChange() {
            const preset = this.presets.find(p => p.name === this.modalPresetName);
            if (preset) {
                this.modalMaterial = preset.material;
                this.modalTemp = preset.temp;
            }
        },

        handleColorSwatchClick(hex) {
            this.modalColorHex = hex;
        },

        handleColorPickerInput(event) {
            this.modalColorHex = event.target.value;
        },

        async saveSlotFromModal() {
            if (!this.colorPickerTarget) return;
            const { slot, instanceIndex } = this.colorPickerTarget;
            const hex = this.modalColorHex;
            const material = this.modalMaterial;
            const temp = this.modalTemp;
            const presetName = this.modalPresetName.trim();

            const rgb = this.hexToRgb(hex);
            if (!rgb) {
                this.showNotification('Invalid color', 'error');
                return;
            }

            const toolParam = slot.tool !== null && slot.tool !== undefined ? `T=${slot.tool}` : `INDEX=${slot.index}`;
            const quotedMaterial = `"${material.replace(/"/g, '\\"')}"`;
            let command = `ACE_SET_SLOT ${toolParam} COLOR="${rgb[0]},${rgb[1]},${rgb[2]}" MATERIAL=${quotedMaterial} TEMP=${temp} INSTANCE=${instanceIndex}`;
            if (presetName) {
                command += ` FILAMENT_SETTINGS_ID="${presetName.replace(/"/g, '\\"')}"`;
            }

            const success = await this.sendGcodeScript(command);
            if (success) {
                this.closeColorPickerModal();
                this.showNotification('Slot updated', 'success');
                setTimeout(() => this.loadStatusForInstance(instanceIndex, 'main'), 500);
            } else {
                this.showNotification('Update failed', 'error');
            }
        },

        async sendGcodeScript(script) {
            try {
                const response = await fetch(`${this.apiBase}/printer/gcode/script`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ script })
                });
                const result = await response.json();
                if (result.error) {
                    console.error('G‑code script error:', result.error);
                    this.showNotification(`Error: ${result.error}`, 'error');
                    return false;
                }
                if (result.result && result.result.success === false) {
                    const errorMsg = result.result.error || result.result.message || 'Command failed';
                    this.showNotification(`Command failed: ${errorMsg}`, 'error');
                    return false;
                }
                this.showNotification(`Command sent: ${script.split(' ')[0]}`, 'success');
                return true;
            } catch (error) {
                console.error('Error sending G‑code script:', error);
                this.showNotification(`Network error: ${error.message}`, 'error');
                return false;
            }
        },

        async setSlotColor(slotIndex, instanceIndex, hex, toolNumber = null, material = '', temp = 0, presetName = '') {
            const rgb = this.hexToRgb(hex);
            if (!rgb) {
                this.showNotification('Invalid color', 'error');
                return false;
            }
            const quotedMaterial = `"${material.replace(/"/g, '\\"')}"`;
            const toolParam = toolNumber !== null ? `T=${toolNumber}` : `INDEX=${slotIndex}`;
            let command = `ACE_SET_SLOT ${toolParam} COLOR="${rgb[0]},${rgb[1]},${rgb[2]}" MATERIAL=${quotedMaterial} TEMP=${temp} INSTANCE=${instanceIndex}`;
            if (presetName) {
                command += ` FILAMENT_SETTINGS_ID="${presetName.replace(/"/g, '\\"')}"`;
            }
            const success = await this.sendGcodeScript(command);
            if (success) {
                setTimeout(() => this.loadStatusForInstance(instanceIndex, 'main'), 500);
            }
            return success;
        },

        async setSlotMaterial(slotIndex, instanceIndex, toolNumber, material, currentColor, currentTemp, presetName = '') {
            const panel = this.instancesPanels.find(p => p.index === instanceIndex);
            const locked = (panel && panel.rfidSyncEnabled) ? (panel.slots.find(s => s.index === slotIndex)?.rfid === 2) : false;
            if (locked) {
                this.showNotification('RFID locked: disable RFID sync to edit', 'error');
                return;
            }
            const hex = this.getColorHex(currentColor);
            let temp;
            if (presetName) {
                const preset = this.presets.find(p => p.name === presetName);
                if (preset) {
                    temp = preset.temp;
                    material = preset.material;
                } else {
                    temp = this.materialOptions[material] || currentTemp || 200;
                }
            } else {
                temp = this.materialOptions[material] || currentTemp || 200;
            }
            const success = await this.setSlotColor(slotIndex, instanceIndex, hex, toolNumber, material, temp, presetName);
            if (success) {
                this.showNotification(`Slot ${slotIndex} updated: ${material}${presetName ? ` (${presetName})` : ''}`, 'success');
            } else {
                this.showNotification(`Failed to update slot ${slotIndex}`, 'error');
            }
        },

        async setSlotTemp(slotIndex, instanceIndex, toolNumber, tempValue, currentColor, currentMaterial, presetName = '') {
            const panel = this.instancesPanels.find(p => p.index === instanceIndex);
            const locked = (panel && panel.rfidSyncEnabled) ? (panel.slots.find(s => s.index === slotIndex)?.rfid === 2) : false;
            if (locked) {
                this.showNotification('RFID locked: disable RFID sync to edit', 'error');
                return;
            }
            const hex = this.getColorHex(currentColor);
            let temp = Number(tempValue);
            if (!Number.isFinite(temp) || temp <= 0 || temp > 300) temp = 200;
            const success = await this.setSlotColor(slotIndex, instanceIndex, hex, toolNumber, currentMaterial, temp, presetName);
            if (success) {
                this.showNotification(`Slot ${slotIndex} temperature set to ${temp}°C`, 'success');
            } else {
                this.showNotification(`Failed to set temperature for slot ${slotIndex}`, 'error');
            }
        },

        commitSlotTemp(slotIndex, instanceIndex, toolNumber, event, currentColor, currentMaterial, presetName = '') {
            const val = event && event.target ? event.target.value : null;
            const parsed = Number(val);
            const temp = (!Number.isFinite(parsed) || parsed <= 0 || parsed > 300) ? 200 : parsed;
            if (event && event.target) event.target.value = temp;
            this.setSlotTemp(slotIndex, instanceIndex, toolNumber, temp, currentColor, currentMaterial, presetName);
            this.updateLocalSlotTemp(instanceIndex, slotIndex, temp);
        },

        updateLocalSlotTemp(instanceIndex, slotIndex, temp) {
            this.instancesPanels = this.instancesPanels.map(panel => {
                if (panel.index !== instanceIndex) return panel;
                const slots = panel.slots.map(slot => {
                    if (slot.index === slotIndex) return { ...slot, temp };
                    return slot;
                });
                return { ...panel, slots };
            });
            if (this.selectedInstance === instanceIndex) {
                this.slots = this.slots.map(slot => {
                    if (slot.index === slotIndex) return { ...slot, temp };
                    return slot;
                });
            }
        },

        getSlotToolNumber(slot, instanceIndex) {
            if (slot && slot.tool !== null && slot.tool !== undefined) {
                const toolNum = Number(slot.tool);
                return Number.isInteger(toolNum) ? toolNum : null;
            }
            const slotIndex = Number(slot?.index);
            if (!Number.isInteger(slotIndex)) return null;
            const panel = this.instancesPanels.find(p => p.index === instanceIndex);
            if (panel && Array.isArray(panel.slots)) {
                const sample = panel.slots.find(s => Number.isInteger(Number(s?.tool)) && Number.isInteger(Number(s?.index)));
                if (sample) {
                    const sampleTool = Number(sample.tool);
                    const sampleIndex = Number(sample.index);
                    const offset = sampleTool - sampleIndex;
                    return offset + slotIndex;
                }
            }
            if (this.instancesPanels.length <= 1) return slotIndex;
            return null;
        },

        isCurrentToolSlot(slot, instanceIndex) {
            if (!Number.isInteger(this.currentTool) || this.currentTool < 0) return false;
            const slotTool = this.getSlotToolNumber(slot, instanceIndex);
            return slotTool !== null && slotTool === this.currentTool;
        },

        // Save/Load slot settings to/from printer
        async saveToPrinter() {
            const settings = { instances: this.instancesPanels.map(inst => ({
                index: inst.index,
                slots: inst.slots.map(slot => ({
                    index: slot.index,
                    material: slot.material,
                    color: slot.color,
                    temp: slot.temp,
                    hex: slot.hex,
                    custom_name: slot.custom_name
                }))
            })) };
            const json = JSON.stringify(settings, null, 2);
            const blob = new Blob([json], { type: 'application/json' });
            const formData = new FormData();
            formData.append('file', blob, 'ace_dashboard_settings.json');
            formData.append('root', 'config');
            try {
                const response = await fetch(`${this.apiBase}/server/files/upload`, {
                    method: 'POST',
                    body: formData
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                this.showNotification('Settings saved to printer', 'success');
            } catch (error) {
                console.error('Save to printer error:', error);
                this.showNotification('Failed to save settings', 'error');
            }
        },

        // ========== ENHANCED LOAD FROM PRINTER WITH WEBSOCKET BLOCKING ==========
        async loadFromPrinter() {
            // Save the original WebSocket handler and temporarily disable it
            let originalHandler = null;
            if (this.ws) {
                originalHandler = this.ws.onmessage;
                this.ws.onmessage = () => {}; // Block incoming status updates
            }

            try {
                const response = await fetch(`${this.apiBase}/server/files/config/ace_dashboard_settings.json`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                if (data.instances && Array.isArray(data.instances)) {
                    const updatedPanels = this.instancesPanels.map(panel => {
                        const savedInst = data.instances.find(i => i.index === panel.index);
                        if (savedInst) {
                            const updatedSlots = panel.slots.map(slot => {
                                const savedSlot = savedInst.slots.find(s => s.index === slot.index);
                                if (savedSlot) {
                                    return {
                                        ...slot,
                                        material: savedSlot.material || slot.material,
                                        color: savedSlot.color || slot.color,
                                        temp: savedSlot.temp !== undefined ? savedSlot.temp : slot.temp,
                                        hex: savedSlot.hex || slot.hex,
                                        custom_name: savedSlot.custom_name || slot.custom_name
                                    };
                                }
                                return slot;
                            });
                            return { ...panel, slots: updatedSlots };
                        }
                        return panel;
                    });
                    this.instancesPanels = updatedPanels;
                    const selectedPanel = updatedPanels.find(p => p.index === this.selectedInstance);
                    if (selectedPanel) this.slots = selectedPanel.slots;
                    this.showNotification('Settings loaded from printer', 'success');

                    // Save the loaded data to the ACE inventory (still with WebSocket blocked)
                    await this.saveInventoryAll();
                    this.showNotification('Settings saved to ACE inventory', 'success');
                }
            } catch (error) {
                console.error('Load from printer error:', error);
                if (!error.message.includes('404')) this.showNotification('Failed to load settings', 'error');
            } finally {
                // Restore the original WebSocket handler and refresh status
                if (this.ws && originalHandler) {
                    this.ws.onmessage = originalHandler;
                }
                await this.loadAllStatus();
            }
        },

        formatTime(minutes) {
            if (!minutes || minutes <= 0) return `0 ${this.t('time.minutes')}`;
            const hours = Math.floor(minutes / 60);
            const mins = minutes % 60;
            if (hours > 0) return `${hours}${this.t('time.hours')} ${mins}${this.t('time.minutesShort')}`;
            return `${mins} ${this.t('time.minutes')}`;
        },

        formatRemainingTime(minutes) {
            if (!minutes || minutes <= 0) return `0${this.t('time.minutesShort')} 0${this.t('time.secondsShort')}`;
            const totalMinutes = Math.floor(minutes);
            const fractionalPart = minutes - totalMinutes;
            const seconds = Math.round(fractionalPart * 60);
            if (totalMinutes > 0) {
                if (seconds > 0) return `${totalMinutes}${this.t('time.minutesShort')} ${seconds}${this.t('time.secondsShort')}`;
                return `${totalMinutes}${this.t('time.minutesShort')}`;
            }
            return `${seconds}${this.t('time.secondsShort')}`;
        },

        showNotification(message, type = 'info') {
            this.notification = { show: true, message, type };
            setTimeout(() => { this.notification.show = false; }, 3000);
        },

        // ========== LocalStorage helpers for custom_name persistence ==========
        _getStorageKey(instanceIndex, slotIndex) {
            return `ace_preset_${instanceIndex}_${slotIndex}`;
        },

        _savePresetToLocalStorage(instanceIndex, slotIndex, presetName) {
            if (presetName) {
                localStorage.setItem(this._getStorageKey(instanceIndex, slotIndex), presetName);
            } else {
                localStorage.removeItem(this._getStorageKey(instanceIndex, slotIndex));
            }
        },

        _loadPresetFromLocalStorage(instanceIndex, slotIndex) {
            return localStorage.getItem(this._getStorageKey(instanceIndex, slotIndex)) || '';
        },

        // Apply preset to slot (with fix for "None" selection)
        async applyPresetToSlot(slot, instanceIndex, presetName) {
            if (!presetName) {
                // Clear the preset name locally
                slot.custom_name = '';
                this._savePresetToLocalStorage(instanceIndex, slot.index, '');

                // Send command to printer without FILAMENT_SETTINGS_ID
                const hex = this.getColorHex(slot.color);
                const success = await this.setSlotColor(
                    slot.index,
                    instanceIndex,
                    hex,
                    slot.tool,
                    slot.material,
                    slot.temp,
                    ''  // empty presetName -> no FILAMENT_SETTINGS_ID in command
                );
                if (success) {
                    this.showNotification(`Preset cleared for slot ${slot.index}`, 'success');
                    // Update local copies
                    this.updateLocalSlotTemp(instanceIndex, slot.index, slot.temp);
                    const panel = this.instancesPanels.find(p => p.index === instanceIndex);
                    if (panel) {
                        const localSlot = panel.slots.find(s => s.index === slot.index);
                        if (localSlot) localSlot.custom_name = '';
                    }
                    if (this.selectedInstance === instanceIndex) {
                        const currentSlot = this.slots.find(s => s.index === slot.index);
                        if (currentSlot) currentSlot.custom_name = '';
                    }
                } else {
                    // Revert UI change on failure (keep old preset name)
                    const oldPreset = this._loadPresetFromLocalStorage(instanceIndex, slot.index);
                    slot.custom_name = oldPreset;
                    this.showNotification('Failed to clear preset', 'error');
                }
                return;
            }

            // Existing logic for non‑empty presetName
            const preset = this.presets.find(p => p.name === presetName);
            if (!preset) {
                this.showNotification(`Preset "${presetName}" not found`, 'error');
                return;
            }
            // Update the slot data immediately for responsive UI
            slot.material = preset.material;
            slot.temp = preset.temp;
            slot.custom_name = presetName;

            // Save to localStorage so it survives a refresh
            this._savePresetToLocalStorage(instanceIndex, slot.index, presetName);

            // Send command to printer
            const hex = this.getColorHex(slot.color);
            const success = await this.setSlotColor(
                slot.index,
                instanceIndex,
                hex,
                slot.tool,
                preset.material,
                preset.temp,
                presetName
            );
            if (success) {
                this.showNotification(`Preset "${presetName}" applied to slot ${slot.index}`, 'success');
                // Refresh local slot list to reflect changes
                this.updateLocalSlotTemp(instanceIndex, slot.index, preset.temp);
                // Also update material in local copy
                const panel = this.instancesPanels.find(p => p.index === instanceIndex);
                if (panel) {
                    const localSlot = panel.slots.find(s => s.index === slot.index);
                    if (localSlot) {
                        localSlot.material = preset.material;
                        localSlot.custom_name = presetName;
                    }
                }
                if (this.selectedInstance === instanceIndex) {
                    const currentSlot = this.slots.find(s => s.index === slot.index);
                    if (currentSlot) {
                        currentSlot.material = preset.material;
                        currentSlot.custom_name = presetName;
                    }
                }
            } else {
                // Revert on failure
                slot.material = slot.material; // keep old
                slot.temp = slot.temp;
                slot.custom_name = slot.custom_name;
                // Remove from localStorage if command failed
                this._savePresetToLocalStorage(instanceIndex, slot.index, '');
            }
        }
    }
}).mount('#app');