/* ============================================================================
   SAMPLE TYPES MANAGEMENT WITH CUSTOM "OTHER" OPTION
   ============================================================================ */

// Store custom sample types
let customSampleTypes = new Set();

/**
 * Initialize sample type checkboxes for a group
 * @param {HTMLElement} groupElement - The group container element
 * @param {number} groupIndex - Index of the group
 */
function initializeSampleTypes(groupElement, groupIndex) {
    const container = groupElement.querySelector('.sample-types-container');
    if (!container) return;
    
    // Fetch sample types from backend
    fetch('/sample-types')
        .then(response => response.json())
        .then(data => {
            renderSampleTypeCheckboxes(container, data.sample_types, groupIndex);
        })
        .catch(error => {
            console.error('Error fetching sample types:', error);
            showToast('⚠️ Failed to load sample types', 'warning');
        });
}

/**
 * Render sample type checkboxes with "Other" option
 * @param {HTMLElement} container - Container element
 * @param {Array} sampleTypes - Array of sample type strings
 * @param {number} groupIndex - Index of the group
 */
function renderSampleTypeCheckboxes(container, sampleTypes, groupIndex) {
    container.innerHTML = ''; // Clear existing
    
    const checkboxContainer = document.createElement('div');
    checkboxContainer.className = 'sample-types-grid';
    checkboxContainer.style.cssText = `
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 10px;
        margin-bottom: 15px;
    `;
    
    // Add all standard sample types
    sampleTypes.forEach(sampleType => {
        const label = createSampleTypeCheckbox(sampleType, groupIndex);
        checkboxContainer.appendChild(label);
    });
    
    container.appendChild(checkboxContainer);
    
    // Add custom "Other" input section
    createOtherSampleInput(container, groupIndex);
    
    // Add "Apply to All Groups" button
    createApplyToAllButton(container, groupIndex);
}

/**
 * Create a checkbox for a sample type
 * @param {string} sampleType - Sample type name
 * @param {number} groupIndex - Index of the group
 * @returns {HTMLElement} Label element containing checkbox
 */
function createSampleTypeCheckbox(sampleType, groupIndex) {
    const label = document.createElement('label');
    label.className = 'sample-type-label';
    label.style.cssText = `
        display: flex;
        align-items: center;
        padding: 8px 12px;
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s;
    `;
    
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.name = `sample-types-${groupIndex}`;
    checkbox.value = sampleType;
    checkbox.className = 'sample-type-checkbox';
    checkbox.style.marginRight = '8px';
    
    // Highlight "Other" option
    if (sampleType === 'Other') {
        checkbox.id = `other-sample-${groupIndex}`;
        checkbox.addEventListener('change', (e) => {
            toggleOtherInput(groupIndex, e.target.checked);
        });
        label.style.border = '2px solid #26a65b';
        label.style.background = '#e9f8ef';
    }
    
    // Add hover effect
    label.addEventListener('mouseenter', () => {
        label.style.background = '#e9ecef';
        label.style.borderColor = '#26a65b';
    });
    
    label.addEventListener('mouseleave', () => {
        if (sampleType !== 'Other') {
            label.style.background = '#f8f9fa';
            label.style.borderColor = '#dee2e6';
        }
    });
    
    const span = document.createElement('span');
    span.textContent = sampleType;
    span.style.fontSize = '14px';
    
    label.appendChild(checkbox);
    label.appendChild(span);
    
    return label;
}

/**
 * Create custom "Other" sample type input
 * @param {HTMLElement} container - Container element
 * @param {number} groupIndex - Index of the group
 */
function createOtherSampleInput(container, groupIndex) {
    const otherSection = document.createElement('div');
    otherSection.id = `other-input-section-${groupIndex}`;
    otherSection.className = 'other-sample-section';
    otherSection.style.cssText = `
        display: none;
        margin-top: 15px;
        padding: 15px;
        background: #fffbeb;
        border: 2px solid #fbbf24;
        border-radius: 8px;
    `;
    
    const label = document.createElement('label');
    label.style.cssText = `
        display: block;
        font-weight: 600;
        margin-bottom: 8px;
        color: #92400e;
    `;
    label.innerHTML = '✏️ Enter Custom Sample Type:';
    
    const inputGroup = document.createElement('div');
    inputGroup.style.cssText = 'display: flex; gap: 10px;';
    
    const input = document.createElement('input');
    input.type = 'text';
    input.id = `custom-sample-input-${groupIndex}`;
    input.placeholder = 'e.g., Saliva, Tears, etc.';
    input.className = 'form-control';
    input.style.cssText = `
        flex: 1;
        padding: 10px;
        border: 1px solid #d97706;
        border-radius: 6px;
        font-size: 14px;
    `;
    
    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'btn btn-success';
    addButton.innerHTML = '➕ Add';
    addButton.style.cssText = `
        padding: 10px 20px;
        background: #26a65b;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 600;
    `;
    
    addButton.addEventListener('click', () => {
        addCustomSampleType(groupIndex);
    });
    
    // Allow Enter key to add
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addCustomSampleType(groupIndex);
        }
    });
    
    inputGroup.appendChild(input);
    inputGroup.appendChild(addButton);
    
    otherSection.appendChild(label);
    otherSection.appendChild(inputGroup);
    
    // Container for custom samples list
    const customList = document.createElement('div');
    customList.id = `custom-samples-list-${groupIndex}`;
    customList.style.cssText = 'margin-top: 12px;';
    otherSection.appendChild(customList);
    
    container.appendChild(otherSection);
}

/**
 * Toggle visibility of "Other" input section
 * @param {number} groupIndex - Index of the group
 * @param {boolean} show - Whether to show or hide
 */
function toggleOtherInput(groupIndex, show) {
    const section = document.getElementById(`other-input-section-${groupIndex}`);
    if (section) {
        section.style.display = show ? 'block' : 'none';
        
        if (show) {
            const input = document.getElementById(`custom-sample-input-${groupIndex}`);
            if (input) input.focus();
        }
    }
}

/**
 * Add custom sample type
 * @param {number} groupIndex - Index of the group
 */
function addCustomSampleType(groupIndex) {
    const input = document.getElementById(`custom-sample-input-${groupIndex}`);
    const customValue = input.value.trim();
    
    if (!customValue) {
        showToast('⚠️ Please enter a sample type name', 'warning');
        return;
    }
    
    // Add to global set
    customSampleTypes.add(customValue);
    
    // Display in list
    displayCustomSample(groupIndex, customValue);
    
    // Clear input
    input.value = '';
    input.focus();
    
    showToast(`✅ Added custom sample: ${customValue}`, 'success');
}

/**
 * Display custom sample in list
 * @param {number} groupIndex - Index of the group
 * @param {string} sampleName - Name of custom sample
 */
function displayCustomSample(groupIndex, sampleName) {
    const listContainer = document.getElementById(`custom-samples-list-${groupIndex}`);
    
    const badge = document.createElement('div');
    badge.className = 'custom-sample-badge';
    badge.style.cssText = `
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        margin: 4px;
        background: #26a65b;
        color: white;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 500;
    `;
    
    const text = document.createElement('span');
    text.textContent = sampleName;
    
    const removeBtn = document.createElement('button');
    removeBtn.innerHTML = '×';
    removeBtn.style.cssText = `
        background: transparent;
        border: none;
        color: white;
        font-size: 18px;
        cursor: pointer;
        padding: 0;
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
    `;
    
    removeBtn.addEventListener('click', () => {
        customSampleTypes.delete(sampleName);
        badge.remove();
        showToast(`Removed: ${sampleName}`, 'info');
    });
    
    badge.appendChild(text);
    badge.appendChild(removeBtn);
    listContainer.appendChild(badge);
}

/**
 * Create "Apply to All Groups" button
 * @param {HTMLElement} container - Container element
 * @param {number} groupIndex - Index of the group
 */
function createApplyToAllButton(container, groupIndex) {
    const buttonContainer = document.createElement('div');
    buttonContainer.style.cssText = 'margin-top: 15px; text-align: center;';
    
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-primary apply-to-all-btn';
    button.innerHTML = '📋 Apply Selected Samples to All Groups';
    button.style.cssText = `
        padding: 12px 24px;
        background: #2563eb;
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        cursor: pointer;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.2s;
    `;
    
    button.addEventListener('mouseenter', () => {
        button.style.background = '#1d4ed8';
        button.style.transform = 'translateY(-2px)';
        button.style.boxShadow = '0 4px 8px rgba(0,0,0,0.15)';
    });
    
    button.addEventListener('mouseleave', () => {
        button.style.background = '#2563eb';
        button.style.transform = 'translateY(0)';
        button.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)';
    });
    
    button.addEventListener('click', () => {
        applyToAllGroups(groupIndex);
    });
    
    buttonContainer.appendChild(button);
    container.appendChild(buttonContainer);
}

/**
 * Get all selected sample types for a group
 * @param {number} groupIndex - Index of the group
 * @returns {Array} Array of selected sample types
 */
function getSelectedSampleTypes(groupIndex) {
    const checkboxes = document.querySelectorAll(`input[name="sample-types-${groupIndex}"]:checked`);
    const selected = Array.from(checkboxes).map(cb => cb.value);
    
    // Add custom samples if "Other" is checked
    const otherChecked = document.getElementById(`other-sample-${groupIndex}`)?.checked;
    if (otherChecked && customSampleTypes.size > 0) {
        customSampleTypes.forEach(customSample => {
            selected.push(customSample);
        });
    }
    
    return selected;
}

/**
 * Apply selected samples to all groups
 * @param {number} sourceGroupIndex - Index of source group
 */
function applyToAllGroups(sourceGroupIndex) {
    const selectedSamples = getSelectedSampleTypes(sourceGroupIndex);
    
    if (selectedSamples.length === 0) {
        showToast('⚠️ Please select at least one sample type', 'warning');
        return;
    }
    
    // Get all group containers
    const allGroups = document.querySelectorAll('.group-card, .group-container');
    let appliedCount = 0;
    
    allGroups.forEach((group, index) => {
        if (index === sourceGroupIndex) return; // Skip source group
        
        // Find checkboxes in this group
        const checkboxes = group.querySelectorAll('.sample-type-checkbox');
        
        // Uncheck all first
        checkboxes.forEach(cb => cb.checked = false);
        
        // Check selected samples
        selectedSamples.forEach(sample => {
            const checkbox = group.querySelector(`.sample-type-checkbox[value="${sample}"]`);
            if (checkbox) {
                checkbox.checked = true;
                appliedCount++;
            }
        });
        
        // Handle "Other" option
        if (customSampleTypes.size > 0) {
            const otherCheckbox = group.querySelector(`#other-sample-${index}`);
            if (otherCheckbox) {
                otherCheckbox.checked = true;
                toggleOtherInput(index, true);
                
                // Add custom samples to this group
                customSampleTypes.forEach(customSample => {
                    displayCustomSample(index, customSample);
                });
            }
        }
    });
    
    const groupCount = allGroups.length - 1; // Exclude source
    showToast(
        `✅ Applied ${selectedSamples.length} sample type(s) to ${groupCount} other group(s)`,
        'success'
    );
}

/**
 * Collect sample types from all groups for submission
 * @returns {Object} Object mapping group index to sample types array
 */
function collectAllSampleTypes() {
    const sampleData = {};
    const allGroups = document.querySelectorAll('.group-card, .group-container');
    
    allGroups.forEach((group, index) => {
        sampleData[index] = getSelectedSampleTypes(index);
    });
    
    return sampleData;
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Initialize sample types for existing groups
    const groups = document.querySelectorAll('.group-card, .group-container');
    groups.forEach((group, index) => {
        initializeSampleTypes(group, index);
    });
    
    console.log('✅ Sample Types Manager initialized');
});

// ============================================================================
// EXPORT FUNCTIONS FOR USE IN OTHER SCRIPTS
// ============================================================================

window.sampleTypesManager = {
    initialize: initializeSampleTypes,
    getSelected: getSelectedSampleTypes,
    collectAll: collectAllSampleTypes,
    applyToAll: applyToAllGroups
};
