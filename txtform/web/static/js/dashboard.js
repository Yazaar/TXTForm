(function() {
    function bubbleToParentClass(startE, classTarget) {
        var target = startE;
        while (!target.classList.contains(classTarget)) {
            target = target.parentElement;
            if (target === null) return null;
        }
        return target;
    }

    function cancelOverlay(e) {
        var target = bubbleToParentClass(e, 'overlay');
        if (!target) return;
        target.classList.remove('show');
    }

    function addCancelOverlayListeners() {
        var btns = document.querySelectorAll('.closeOverlayBTN');
        for (let i = 0; i < btns.length; i++) {
            btns[i].addEventListener('click', function() { cancelOverlay(this); });
        }
    }

    function addEditListeners() {
        var btns = document.querySelectorAll('.editResponse');
        for (let i = 0; i < btns.length; i++) {
            btns[i].addEventListener('click', function() { editResponse(this); });
        }

        btns = document.querySelectorAll('.editAccount');
        for (let i = 0; i < btns.length; i++) {
            btns[i].addEventListener('click', function() { editAccount(this); });
        }

        btns = document.querySelectorAll('.editFlow');
        for (let i = 0; i < btns.length; i++) {
            btns[i].addEventListener('click', function() { editFlow(this); });
        }
    }

    /**************
     * MY ACCOUNT *
     **************/
    var myAccountOverlay = document.querySelector('#myAccountOverlay');
    var myAccountUsername = document.querySelector('#myAccountUsername');
    var myAccountError = document.querySelector('#myAccountError');
    var saveMyAccountBTN = document.querySelector('#saveMyAccountBTN');

    document.querySelector('#myAccountBTN').addEventListener('click', function() {
        myAccountUsername.value = myAccountUsername.getAttribute('data-username') || '';
        myAccountError.innerHTML = '';
        myAccountOverlay.classList.add('show');
    });

    document.querySelector('#saveMyAccountBTN').addEventListener('click', async function() {
        var username = myAccountUsername.value;
        if (this.classList.contains('disabled') || myAccountUsername.getAttribute('data-username') === username) return;

        if (username.length === 0) {
            myAccountError.innerText = 'Fill in a username';
            return;
        }

        if (!/^[a-zA-Z0-9]+$/.test(username)) {
            myAccountError.innerText = 'Allowed: a-z, A-Z, 0-9';
            return;
        }

        this.classList.add('disabled');
        var thisE = this;
        setTimeout(() => {
            thisE.classList.remove('disabled');
        }, 5000);

        try {
            var resp = await fetch('/myaccount/save', {
                method: 'post',
                body: JSON.stringify({
                    username: username
                })
            });
        } catch (e) {
            myAccountError.innerText = 'Server error';
            return;
        }

        try {
            var data = await resp.json();
        } catch (e) {
            myAccountError.innerText = 'Bad response error';
            return;
        }

        if (!data.success) {
            if (data.message) myAccountError.innerText = data.message;
            else myAccountError.innerText = 'Save failed';
            return;
        }

        myAccountUsername.setAttribute('data-username', username);
        myAccountOverlay.classList.remove('show');
    });

    /***************
     * CONNECTIONS *
     ***************/
    var connectNewAccountOverlay = document.querySelector('#connectNewAccountOverlay');
    var disconnectAccountType = document.querySelector('#disconnectAccountType');
    var disconnectAccountBTN = document.querySelector('#disconnectAccountBTN');
    var disconnectAccountOverlay = document.querySelector('#disconnectAccountOverlay');

    document.querySelector('#connectNewAccount').addEventListener('click', function() {
        connectNewAccountOverlay.classList.add('show');
    });

    function editAccount(e) {
        var target = bubbleToParentClass(e, 'card');
        if (!target) return;
        var targetID = target.getAttribute('data-id');
        var targetType = target.getAttribute('data-accountType');
        var targetName = target.getAttribute('data-name');
        if (!targetID || !targetType) return;
        disconnectAccountType.innerText = targetType + ': ' + targetName;
        disconnectAccountBTN.href = '/apis/' + targetType + '/disconnect/' + targetID;
        disconnectAccountOverlay.classList.add('show');
    }

    /*************
     * RESPONSES *
     *************/
    var responseComponentsE = document.querySelector('#responseComponents');
    var responseOverlayE = document.querySelector('#responseOverlay');
    var responseComponentOverlayE = document.querySelector('#responseComponentOverlay');
    var responseComponentSelect = document.querySelector('#responseComponentSelect');
    var clickedAddComponentE = null;
    var editedResponseID = null;

    var newResponseError = document.querySelector('#newResponseError');
    var newResponseForm = document.querySelector('#newResponseForm');
    var newResponseName = document.querySelector('#newResponseName');
    var newResponseOverlay = document.querySelector('#newResponseOverlay');
    var deleteResponseForm = document.querySelector('#deleteResponseForm');
    var deleteResponseIDInput = deleteResponseForm.querySelector('#deleteResponseID');
    var saveResponseError = document.querySelector('#saveResponseError');
    var responseNameInput = document.querySelector('#responseNameInput');
    var spotifyAccountPickerE = document.querySelector('#spotifyAccountPicker');
    var spotifyAccountSelect = spotifyAccountPickerE.querySelector('select');


    document.querySelector('#cancelResponseComponent').addEventListener('click', function() {
        responseOverlayE.classList.add('show');
    });

    document.querySelector('#saveResponseComponent').addEventListener('click', async function() {
        if (this.classList.contains('disabled')) return;
        var v = responseComponentSelect.value;
        if (v === '*') return;

        this.classList.add('disabled');
        var thisE = this;
        setTimeout(() => {
            thisE.classList.remove('disabled');
        }, 5000);

        var requires = responseComponentSelect[responseComponentSelect.selectedIndex].getAttribute('data-requires') || '';
        requires = requires.split('.');
        var query = '';
        if (requires.includes('spotifyAccount')) {
            if (spotifyAccountSelect.value === '*') return;
            query = '?spotify_id=' + spotifyAccountSelect.value;
        }

        var resp = await fetch('/render/component/' + v + query);
        var data = await resp.text();
        if (data.length === 0) return;

        var e = document.createElement('div');
        e.innerHTML = data;
        e = e.firstChild

        clickedAddComponentE.parentElement.parentElement.insertBefore(e, clickedAddComponentE.parentElement);
        renderComponents();
        responseComponentOverlayE.classList.remove('show');
        responseOverlayE.classList.add('show');
    });

    document.querySelector('#saveResponse').addEventListener('click', async function() {
        if (this.classList.contains('disabled')) return;
        var componentsE = responseComponentsE.querySelectorAll('.component');
        var components = [];
        var respName = responseNameInput.value;

        if (respName.length === 0) {
            saveResponseError.innerText = 'Input a response name';
            return;
        }

        for (let i = 0; i < componentsE.length; i++) {
            let identifier = componentsE[i].getAttribute('data-identifier');
            if (!identifier) continue;
            let inputEs = componentsE[i].querySelectorAll('input[name]');
            if (inputEs.length === 0) continue;
            let values = {};
            for (let j = 0; j < inputEs.length; j++) {
                let vName = inputEs[j].getAttribute('name');
                let v = inputEs[j].getAttribute('data-real-value');
                if (!v) v = inputEs[j].value;
                values[vName] = v;
            }
            components.push({type: identifier, values: values});
        }

        this.classList.add('disabled');
        var thisE = this;
        setTimeout(() => {
            thisE.classList.remove('disabled');
        }, 5000);

        try {
            var resp = await fetch('/responses/save', {
                method: 'post',
                body: JSON.stringify({
                    components: components,
                    respID: editedResponseID,
                    label: respName
                })
            });
        } catch (e) {
            saveResponseError.innerText = 'Server error';
            return;
        }

        try {
            var data = await resp.json();
        } catch (e) {
            saveResponseError.innerText = 'Server response error';
            return;
        }

        if (!data.success) {
            if (data.message) saveResponseError.innerText = data.message;
            else saveResponseError.innerText = 'Save failed';
            return;
        }

        var cardE = document.querySelector('#responses > .card[data-id="' + editedResponseID + '"]');
        if (cardE && cardE.getAttribute('data-name') !== respName) {
            cardE.setAttribute('data-name', respName);
            cardE.innerText = respName;
            return;
        }

        responseOverlayE.classList.remove('show');
    });

    document.querySelector('#deleteResponse').addEventListener('click', function() {
        if (this.classList.contains('disabled')) return;
        this.classList.add('disabled');
        var thisE = this;
        setTimeout(() => {
            thisE.classList.remove('disabled');
        }, 5000);
        deleteResponseIDInput.value = editedResponseID;
        deleteResponseForm.submit()
    });

    responseComponentSelect.addEventListener('change', function() {
        var requires = this.options[this.selectedIndex].getAttribute('data-requires') || '';
        requires = requires.split('.');
        if (requires.includes('spotifyAccount')) {
            spotifyAccountPickerE.classList.add('show');
            spotifyAccountSelect.value = '*';
        }
        else spotifyAccountPickerE.classList.remove('show');
    });

    document.querySelector('#showNewResponseOverlayBTN').addEventListener('click', function() {
        newResponseOverlay.classList.add('show');
        newResponseName.value = '';
        newResponseError.innerHTML = '';
    });

    document.querySelector('#newResponseBTN').addEventListener('click', async function() {
        if (this.classList.contains('disabled')) return;

        var requestedName = newResponseName.value;
        if (requestedName.length === 0) {
            newResponseError.innerText = 'Insert a name';
            return;
        }

        if (!/^[a-zA-Z0-9]+$/.test(requestedName)) {
            newResponseError.innerText = 'Allowed in name: a-z, A-Z, 0-9';
            return;
        }

        this.classList.add('disabled');
        var thisE = this;
        setTimeout(() => {
            thisE.classList.remove('disabled');
        }, 5000);

        try {
            var resp = await fetch('/responses/verify?name=' + requestedName, {method: 'post'});
        } catch (e) {
            newResponseError.innerText = 'Failed contacting server';
            return;
        }

        try {
            var data = await resp.json();
        } catch (e) {
            newResponseError.innerText = 'Invalid server response';
            return;
        }

        if (!data.success) {
            if (data.message) newResponseError.innerText = data.message;
            else newResponseError.innerText = 'Server error';
            return;
        }

        newResponseName.value = requestedName;
        newResponseForm.submit();
    });

    function renderComponents() {
        var elements = responseComponentsE.querySelectorAll('.component');
        for (let i = 0; i < elements.length; i++) {
            if (elements[i].querySelector('.addComponent')) continue;
            let addComponent = document.createElement('div');
            addComponent.classList.add('addComponent');
            addComponent.innerText = '▼';
            addComponent.addEventListener('click', function() { onNewComponentClick(this); });
            elements[i].appendChild(addComponent);
        }
        addDeleteComponentListeners();
    }

    function onNewComponentClick(e) {
        clickedAddComponentE = e;
        responseComponentSelect.value = '*';
        responseComponentSelect.dispatchEvent(new Event('change'));
        responseComponentOverlayE.classList.add('show');
        responseOverlayE.classList.remove('show');
    }

    async function getComponents() {
        var resp = await fetch('/render/components/' + editedResponseID);
        var data = await resp.text();
        responseComponentsE.innerHTML = data + '<div class="component blankComponent"></div>';
        renderComponents()
    }

    function editResponse(e) {
        var target = bubbleToParentClass(e, 'card');
        if (!target) return;
        var targetID = target.getAttribute('data-id');
        var targetName = target.getAttribute('data-name');
        if (!targetID || !targetName) return;
        editedResponseID = targetID;
        saveResponseError.innerHTML = '';
        responseNameInput.value = targetName;
        getComponents().then(() => { responseOverlayE.classList.add('show'); });
    }

    async function deleteClickedComponent(componentDeleteBTN) {
        var componentE = bubbleToParentClass(componentDeleteBTN, 'component');
        if (!componentE) return;

        componentE.parentElement.removeChild(componentE);
        saveResponseError.innerHTML = '';
    }

    function addDeleteComponentListeners() {
        var btns = document.querySelectorAll('.button.deleteComponent');
        for (let i = 0; i < btns.length; i++) {
            if (btns[i].getAttribute('data-handled') === '1') continue;
            btns[i].setAttribute('data-handled', '1');
            btns[i].addEventListener('click', function() { deleteClickedComponent(this); });
        }
    }

    async function getComponentOptions() {
        var resp = await fetch('/render/component/component_options')
        var data = await resp.text();
        responseComponentSelect.innerHTML = data;
    }

    /*********
     * FLOWS *
     *********/

    var editedFlowID = null;
    var flowOverlay = document.querySelector('#flowOverlay');
    var saveFlowError = document.querySelector('#saveFlowError');
    var flowStates = document.querySelector('#flowStates');
    var flowNameInput = document.querySelector('#flowNameInput');
    var newFlowStateCache = null;
    var deleteFlowIDInput = document.querySelector('#deleteFlowID');
    var deleteFlowForm = document.querySelector('#deleteFlowForm');

    var newFlowOverlay = document.querySelector('#newFlowOverlay');
    var newFlowForm = document.querySelector('#newFlowForm');
    var newFlowName = document.querySelector('#newFlowName');
    var newFlowError = document.querySelector('#newFlowError');

    function enableToggles() {
        var toggles = document.querySelectorAll('.toggle');
        for (let i = 0; i < toggles.length; i++) {
            if (toggles[i].getAttribute('data-processed') === '1') continue;
            toggles[i].setAttribute('data-processed', '1');
            toggles[i].addEventListener('click', function() {
                onToggleClick(this, onToggleClickCallback);
            });
        }
    }

    function onToggleClick(e, onClickCallback) {
        if (e.classList.contains('timeout')) return;
        e.classList.add('timeout');
        var enabled = e.classList.toggle('enabled');
        onClickCallback(e, enabled);
        setTimeout(() => {
            e.classList.remove('timeout');
        }, 2000);
    }

    function onToggleClickCallback(e, enabled) {
        var card = bubbleToParentClass(e, 'card');
        if (!card) return;
        var flowID = card.getAttribute('data-id');
        if (!flowID) return;
        fetch('/flows/toggle',  {
            method: 'post',
            body: JSON.stringify({
                flowID: flowID,
                enabled: enabled
            })
        });
    }

    function enableCopyLinks() {
        var es = document.querySelectorAll('.copyLink');
        for (let i = 0; i < es.length; i++) {
            if (es[i].getAttribute('data-processed') === '1') continue;
            es[i].setAttribute('data-processed', '1');
            es[i].addEventListener('click', function() {
                onCopyFlowLink(this);
            });
        }
    }

    function onCopyFlowLink(e) {
        var card =  bubbleToParentClass(e, 'card');
        if (!card) return;
        var flowName = card.getAttribute('data-name');
        var accountName = myAccountUsername.getAttribute('data-username');
        if  (!flowName || !accountName)  return;
        var flowURL = location.origin + '/u/'  + accountName.toLowerCase() + '/flow/'  + flowName.toLowerCase() + '/text';
        navigator.clipboard.writeText(flowURL);
        e.classList.add('copied');
        setTimeout(() => {
            e.classList.remove('copied');
        }, 2000);
    }

    function editFlow(e) {
        var target = bubbleToParentClass(e, 'card');
        if (!target) return;
        var targetID = target.getAttribute('data-id');
        var targetName = target.getAttribute('data-name');
        if (!targetID || !targetName) return;
        editedFlowID = targetID;
        saveFlowError.innerHTML = '';
        responseNameInput.value = targetName;
        flowNameInput.value = targetName;
        newFlowStateCache = null;
        getFlowStates().then(() => { flowOverlay.classList.add('show'); });
    }

    async function getFlowStates() {
        var resp = await fetch('/render/flows/' + editedFlowID);
        var data = await resp.text();
        flowStates.innerHTML = data;
        flowStatesListeners();
    }

    function flowStatesListeners() {
        var es = document.querySelectorAll('.flowCondition');
        for (let i = 0; i < es.length; i++) {
            if (es[i].getAttribute('data-handled') !== '1') {
                es[i].setAttribute('data-handled', '1');
                es[i].addEventListener('change', function() { stateConditionChanged(this); })
            }
        }

        es = document.querySelectorAll('.addState');
        for (let i = 0; i < es.length; i++) {
            if (es[i].getAttribute('data-handled') !== '1') {
                es[i].setAttribute('data-handled', '1');
                es[i].addEventListener('click', function() { addFlowState(this); })
            }
        }

        es = document.querySelectorAll('.deleteState');
        for (let i = 0; i < es.length; i++) {
            if (es[i].getAttribute('data-handled') !== '1') {
                es[i].setAttribute('data-handled', '1');
                es[i].addEventListener('click', function() { deleteFlowState(this); })
            }
        }
    }

    async function addFlowState(e) {
        if (e.classList.contains('disabled')) return;
        e.classList.add('disabled');
        setTimeout(() => {
            e.classList.remove('disabled');
        }, 5000);
        var flowState = bubbleToParentClass(e, 'flowState');
        if (!flowState) return;
        var newFlowState = await getDefaultFlowState();
        if (newFlowState === null) return;
        flowState.parentElement.insertBefore(newFlowState, flowState);
        flowStatesListeners();
    }

    async function deleteFlowState(e) {
        var flowStateE = bubbleToParentClass(e, 'flowState');
        if (!flowStateE) return;

        flowStateE.parentElement.removeChild(flowStateE);
        saveFlowError.innerHTML = '';
    }

    function stateConditionChanged(e)  {
        var val  = e.value;
        var flowState = bubbleToParentClass(e, 'flowState');
        if (!flowState) return;
        var twitchCondition = flowState.querySelector('.twitchCondition');
        var twitchPicker = flowState.querySelector('.twitchPicker');
        if (!twitchCondition || !twitchPicker) return;
        twitchCondition.value = '*';
        if (val  === 'twitchLive') twitchPicker.classList.add('show');
        else twitchPicker.classList.remove('show');
    }

    async function getDefaultFlowState() {
        if (!newFlowStateCache) {
            try {
                var resp = await fetch('/render/flow/state');
                newFlowStateCache = await resp.text();
            } catch (e) { return null; }
        }
        var e = document.createElement('div');
        e.innerHTML = newFlowStateCache;
        return e.firstChild;
    }

    document.querySelector('#showNewFlowOverlayBTN').addEventListener('click', function() {
        newFlowOverlay.classList.add('show');
        newFlowName.value = '';
        newFlowError.innerHTML = '';
    });

    document.querySelector('#newFlowBTN').addEventListener('click', async function() {
        if (this.classList.contains('disabled')) return;

        var requestedName = newFlowName.value;
        if (requestedName.length === 0) {
            newFlowError.innerText = 'Insert a name';
            return;
        }

        if (!/^[a-zA-Z0-9]+$/.test(requestedName)) {
            newFlowError.innerText = 'Allowed in name: a-z, A-Z, 0-9';
            return;
        }

        this.classList.add('disabled');
        var thisE = this;
        setTimeout(() => {
            thisE.classList.remove('disabled');
        }, 5000);

        try {
            var resp = await fetch('/flows/verify?name=' + requestedName, {method: 'post'});
        } catch (e) {
            newFlowError.innerText = 'Failed contacting server';
            return;
        }

        try {
            var data = await resp.json();
        } catch (e) {
            newFlowError.innerText = 'Invalid server response';
            return;
        }

        if (!data.success) {
            if (data.message) newFlowError.innerText = data.message;
            else newFlowError.innerText = 'Server error';
            return;
        }

        newFlowName.value = requestedName;
        newFlowForm.submit();
    });

    document.querySelector('#deleteFlow').addEventListener('click', function() {
        if (this.classList.contains('disabled')) return;
        this.classList.add('disabled');
        var thisE = this;
        setTimeout(() => {
            thisE.classList.remove('disabled');
        }, 5000);
        deleteFlowIDInput.value = editedFlowID;
        deleteFlowForm.submit();
    });

    document.querySelector('#saveFlow').addEventListener('click', async function() {
        if (this.classList.contains('disabled')) return;
        var stateEs = flowStates.querySelectorAll('.flowState');
        var states = [];
        var flowName = flowNameInput.value;

        if (flowName.length === 0) {
            saveFlowError.innerText = 'Input a flow name';
            return;
        }

        for (let i = 0; i < stateEs.length; i++) {
            let inputEs = stateEs[i].querySelectorAll('input[name], select[name]');
            if (inputEs.length === 0) continue;
            let values = {};
            for (let j = 0; j < inputEs.length; j++) {
                let vName = inputEs[j].getAttribute('name');
                values[vName] = inputEs[j].value;
            }
            let condition = values.condition;
            let response_id = values.response_id;
            if (!condition || !response_id)  {
                saveFlowError.innerText = 'Condition or response missing';
                return;
            }
            if (condition === 'twitchLive') {
                if (!values.twitch_id) {
                    saveFlowError.innerText = 'Twitch is missing';
                    return;
                } else if (values.twitch_id === '*') {
                    saveFlowError.innerText = 'Select Twitch';
                    return;
                }
            } else if (values.twitch_id) {
                delete values.twitch_id;
            }
            if (response_id === '*') {
                saveFlowError.innerText = 'Select response';
                return;
            }
            delete values.response_id;
            delete values.condition;
            states.push({condition: condition, response_id: response_id, values: values});
        }

        this.classList.add('disabled');
        var thisE = this;
        setTimeout(() => {
            thisE.classList.remove('disabled');
        }, 5000);

        try {
            var resp = await fetch('/flows/save', {
                method: 'post',
                body: JSON.stringify({
                    states: states,
                    flowID: editedFlowID,
                    label: flowName
                })
            });
        } catch (e) {
            saveFlowError.innerText = 'Server error';
            return;
        }

        try {
            var data = await resp.json();
        } catch (e) {
            saveFlowError.innerText = 'Server response error';
            return;
        }

        if (!data.success) {
            if (data.message) saveFlowError.innerText = data.message;
            else saveFlowError.innerText = 'Save failed';
            return;
        }

        var cardE = document.querySelector('#flows > .card[data-id="' + editedFlowID + '"]');
        if (cardE && cardE.getAttribute('data-name') !== flowName) {
            cardE.setAttribute('data-name', flowName);
            cardE.querySelector('.name').innerText = flowName;
            return;
        }

        flowOverlay.classList.remove('show');
    });

    /***********
     * STARTUP *
     ***********/

    getComponentOptions();
    addCancelOverlayListeners();
    addEditListeners();
    enableToggles();
    enableCopyLinks();
})();
