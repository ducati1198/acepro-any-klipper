// ValgACE Dashboard JavaScript

const { createApp } = Vue;

createApp({
    data() {
        return {
            currentLanguage: 'en',
            translations: {
                // same as before – keep unchanged
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
                        type: 'Type',
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
                            tempRange: 'Temperature must be between 20 and 55°C',
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
            dryingHours: 0,
            dryingMinutes: 0,
            
            // Local countdown timer
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
            materialOptions: {
                'PLA': 200,
                'PETG': 235,
                'ABS': 240,
                'ASA': 245,
                'PVA': 185,
                'HIPS': 230,
                'PC': 260,
                'PLA+': 210,
                'PLA Glow': 210,
                'PLA High Speed': 215,
                'PLA Marble': 205,
                'PLA Matte': 205,
                'PLA SE': 210,
                'PLA Silk': 215,
                'TPU': 210
            },
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
            
            presetFeedLength: ACE_DASHBOARD_CONFIG?.defaults?.presetFeedLength || 50,
            presetRetractLength: ACE_DASHBOARD_CONFIG?.defaults?.presetRetractLength || 50,
            
            notification: {
                show: false,
                message: '',
                type: 'info'
            },

            // Preset library
            showPresetLibrary: false,
            presets: []  // now each element has { name, material, temp }
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
            this.setSlotColor(slot.index, instanceIndex, normalized, slot.tool, slot.material || slot.type || '', slot.temp);
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
                if (panel.index !== instanceIndex) {
                    return panel;
                }
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

        // Timer helpers
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
        
        // WebSocket Connection
        connectWebSocket() {
            const wsUrl = getWebSocketUrl();
            
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                this.wsConnected = true;
                this.showNotification(this.t('notifications.websocketConnected'), 'success');
                this.subscribeToStatus();
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
                params: {
                    objects: {
                        "ace": null
                    }
                },
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
        
        // API Calls
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
                if (
                    !Number.isInteger(this.selectedInstance) ||
                    !this.instanceOptions.find(opt => opt.index === this.selectedInstance)
                ) {
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
                        slots: slotsArr.map(slot => ({
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
                            customFeedLength: ACE_DASHBOARD_CONFIG?.defaults?.feedLength || 50,
                            customFeedSpeed: ACE_DASHBOARD_CONFIG?.defaults?.feedSpeed || 25,
                            customRetractLength: ACE_DASHBOARD_CONFIG?.defaults?.retractLength || 50,
                            customRetractSpeed: ACE_DASHBOARD_CONFIG?.defaults?.retractSpeed || 25
                        })),
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
                    this.slots = data.slots.map(slot => ({
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
                        customFeedLength: ACE_DASHBOARD_CONFIG?.defaults?.feedLength || 50,
                        customFeedSpeed: ACE_DASHBOARD_CONFIG?.defaults?.feedSpeed || 25,
                        customRetractLength: ACE_DASHBOARD_CONFIG?.defaults?.retractLength || 50,
                        customRetractSpeed: ACE_DASHBOARD_CONFIG?.defaults?.retractSpeed || 25
                    }));
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
                if (dryer.status !== undefined) {
                    this.dryerStatus.status = dryer.status;
                }
                if (dryer.target_temp !== undefined) this.dryerStatus.target_temp = dryer.target_temp;
            }
            if (data.dryer_target_temp !== undefined) this.dryerStatus.target_temp = data.dryer_target_temp;
            
            // Timer management
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

        async saveInventoryAll() {
            let anySuccess = false;
            const instances = this.instanceOptions.length > 0 ? this.instanceOptions : [{ index: this.selectedInstance || 0 }];
            for (const inst of instances) {
                const success = await this.executeCommand('ACE_SAVE_INVENTORY', { INSTANCE: inst.index });
                if (success) anySuccess = true;
            }
            if (anySuccess) {
                this.showNotification(this.t('notifications.commandSuccess', { command: 'ACE_SAVE_INVENTORY' }), 'success');
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

        async setSlotColor(slotIndex, instanceIndex, hex, toolNumber = null, material = '', temp = 0) {
            const rgb = this.hexToRgb(hex);
            if (!rgb) {
                this.showNotification('Invalid color', 'error');
                return false;
            }
            
            // Properly quote the material name (always quote for safety)
            const quotedMaterial = `"${material.replace(/"/g, '\\"')}"`;
            
            const toolParam = toolNumber !== null ? `T=${toolNumber}` : `INDEX=${slotIndex}`;
            const command = `ACE_SET_SLOT ${toolParam} COLOR="${rgb[0]},${rgb[1]},${rgb[2]}" MATERIAL=${quotedMaterial} TEMP=${temp} INSTANCE=${instanceIndex}`;
            
            const success = await this.sendGcodeScript(command);
            if (success) {
                setTimeout(() => this.loadStatusForInstance(instanceIndex, 'main'), 500);
            }
            return success;
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

        async setSlotMaterial(slotIndex, instanceIndex, toolNumber, material, currentColor, currentTemp) {
            const panel = this.instancesPanels.find(p => p.index === instanceIndex);
            const locked = (panel && panel.rfidSyncEnabled) ? (panel.slots.find(s => s.index === slotIndex)?.rfid === 2) : false;
            if (locked) {
                this.showNotification('RFID locked: disable RFID sync to edit', 'error');
                return;
            }
            const hex = this.getColorHex(currentColor);
            const preset = this.presets.find(p => p.name === material);
            let temp;
            if (preset) {
                temp = preset.temp;
            } else {
                temp = this.materialOptions[material] || currentTemp || 200;
            }
            const success = await this.setSlotColor(slotIndex, instanceIndex, hex, toolNumber, material, temp);
            if (success) {
                this.showNotification(`Slot ${slotIndex} updated: ${material}`, 'success');
            } else {
                this.showNotification(`Failed to update slot ${slotIndex}`, 'error');
            }
        },

        async setSlotTemp(slotIndex, instanceIndex, toolNumber, tempValue, currentColor, currentMaterial) {
            const panel = this.instancesPanels.find(p => p.index === instanceIndex);
            const locked = (panel && panel.rfidSyncEnabled) ? (panel.slots.find(s => s.index === slotIndex)?.rfid === 2) : false;
            if (locked) {
                this.showNotification('RFID locked: disable RFID sync to edit', 'error');
                return;
            }
            const hex = this.getColorHex(currentColor);
            let temp = Number(tempValue);
            if (!Number.isFinite(temp) || temp <= 0 || temp > 300) temp = 200;
            const success = await this.setSlotColor(slotIndex, instanceIndex, hex, toolNumber, currentMaterial, temp);
            if (success) {
                this.showNotification(`Slot ${slotIndex} temperature set to ${temp}°C`, 'success');
            } else {
                this.showNotification(`Failed to set temperature for slot ${slotIndex}`, 'error');
            }
        },

        commitSlotTemp(slotIndex, instanceIndex, toolNumber, event, currentColor, currentMaterial) {
            const val = event && event.target ? event.target.value : null;
            const parsed = Number(val);
            const temp = (!Number.isFinite(parsed) || parsed <= 0 || parsed > 300) ? 200 : parsed;
            if (event && event.target) event.target.value = temp;
            this.setSlotTemp(slotIndex, instanceIndex, toolNumber, temp, currentColor, currentMaterial);
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
        
        // Preset library methods (updated to handle three fields)
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
                        // Extract name: filament_settings_id, then name, then filename
                        let name = data.filament_settings_id || data.name || file.name.replace(/\.json$/, '');
                        if (Array.isArray(name)) name = name[0];
                        // Extract material: filament_type
                        let material = data.filament_type || '';
                        if (Array.isArray(material)) material = material[0];
                        // Extract temperature: nozzle_temperature
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

        // Colour picker modal methods
        openColorPickerModal(slot, instanceIndex) {
            this.colorPickerTarget = { slot: { ...slot }, instanceIndex };
            this.modalMaterial = slot.material || slot.type || '';
            this.modalTemp = slot.temp || 0;
            this.modalColorHex = this.getColorHex(slot.color);
            this.showColorPickerModal = true;
        },

        closeColorPickerModal() {
            this.showColorPickerModal = false;
            this.colorPickerTarget = null;
        },

        onModalMaterialChange() {
            const selected = this.modalMaterial;
            const preset = this.presets.find(p => p.name === selected);
            if (preset) {
                this.modalTemp = preset.temp;
            } else {
                const builtInTemp = this.materialOptions[selected];
                if (builtInTemp !== undefined) {
                    this.modalTemp = builtInTemp;
                }
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
            const success = await this.setSlotColor(slot.index, instanceIndex, hex, slot.tool, material, temp);
            if (success) {
                this.closeColorPickerModal();
                this.showNotification('Slot updated', 'success');
            } else {
                this.showNotification('Update failed', 'error');
            }
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
                    hex: slot.hex
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

        async loadFromPrinter() {
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
                                        hex: savedSlot.hex || slot.hex
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
                }
            } catch (error) {
                console.error('Load from printer error:', error);
                if (!error.message.includes('404')) this.showNotification('Failed to load settings', 'error');
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
        }
    }
}).mount('#app');