/* ============================================================================
   RODENT STUDY PLANNER - JAVASCRIPT
   ============================================================================ */

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function setButtonLoading(button, loading) {
    if (loading) {
        button.classList.add('loading');
        button.disabled = true;
        const originalText = button.innerHTML;
        button.dataset.originalText = originalText;
        button.innerHTML = '<span class="spinner"></span> Processing...';
    } else {
        button.classList.remove('loading');
        button.disabled = false;
        button.innerHTML = button.dataset.originalText;
    }
}

// ============================================================================
// COLLECT STUDY PLAN DATA
// ============================================================================

function collectStudyPlanData() {
    // Collect all phase data
    const phases = [];
    const phaseCards = document.querySelectorAll('.phase-card');
    
    phaseCards.forEach((card, index) => {
        const title = card.querySelector('.phase-header h3').textContent;
        const duration = card.querySelector('.phase-duration').value;
        const description = card.querySelector('.phase-description').value;
        
        phases.push({
            name: `Phase ${index + 1}`,
            title: title,
            duration: duration,
            description: description
        });
    });
    
    // Collect main study data
    const studyData = {
        study_title: document.getElementById('study-title').value || 'Untitled Study',
        pi_name: document.getElementById('pi-name').value || 'Not specified',
        institution: document.getElementById('institution').value || 'Not specified',
        study_type: document.getElementById('study-type').value || 'Rodent Pharmacology Study',
        study_objective: document.getElementById('study-objective').value || '',
        study_duration: document.getElementById('study-duration').value || '12',
        study_start_date: document.getElementById('start-date').value || '',
        special_considerations: document.getElementById('special-considerations').value || 'None',
        phases: phases,
        groups: [] // This will be filled from your existing group data if needed
    };
    
    return studyData;
}

// ============================================================================
// EXPORT TO PDF
// ============================================================================

async function exportStudyPlanPDF() {
    const button = document.getElementById('export-study-pdf');
    
    try {
        setButtonLoading(button, true);
        
        const studyData = collectStudyPlanData();
        
        const response = await fetch('/study-plan/pdf', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(studyData)
        });
        
        if (!response.ok) {
            throw new Error('Failed to generate PDF');
        }
        
        // Download the PDF
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `study_plan_${Date.now()}.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        
        showToast('✅ PDF exported successfully!', 'success');
        
    } catch (error) {
        console.error('PDF export error:', error);
        showToast('❌ Failed to export PDF. Please try again.', 'error');
    } finally {
        setButtonLoading(button, false);
    }
}

// ============================================================================
// EXPORT TO WORD
// ============================================================================

async function exportStudyPlanDOC() {
    const button = document.getElementById('export-study-doc');
    
    try {
        setButtonLoading(button, true);
        
        const studyData = collectStudyPlanData();
        
        const response = await fetch('/study-plan/docx', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(studyData)
        });
        
        if (!response.ok) {
            throw new Error('Failed to generate Word document');
        }
        
        // Download the DOCX
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `study_plan_${Date.now()}.docx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        
        showToast('✅ Word document exported successfully!', 'success');
        
    } catch (error) {
        console.error('DOCX export error:', error);
        showToast('❌ Failed to export Word document. Please try again.', 'error');
    } finally {
        setButtonLoading(button, false);
    }
}

// ============================================================================
// CLEAR FORM
// ============================================================================

function clearStudyPlanForm() {
    if (confirm('Are you sure you want to clear all fields?')) {
        document.getElementById('study-title').value = '';
        document.getElementById('pi-name').value = '';
        document.getElementById('institution').value = '';
        document.getElementById('study-type').value = '';
        document.getElementById('study-objective').value = '';
        document.getElementById('study-duration').value = '12';
        document.getElementById('start-date').value = '';
        document.getElementById('special-considerations').value = '';
        
        // Reset phases to defaults
        const phaseDurations = document.querySelectorAll('.phase-duration');
        const defaultDurations = [2, 1, 6, 3];
        phaseDurations.forEach((input, index) => {
            input.value = defaultDurations[index] || 1;
        });
        
        const phaseDescriptions = document.querySelectorAll('.phase-description');
        phaseDescriptions.forEach(textarea => {
            textarea.value = '';
        });
        
        showToast('Form cleared successfully', 'success');
    }
}

// ============================================================================
// AUTO-CALCULATE TOTAL DURATION
// ============================================================================

function updateTotalDuration() {
    const phaseDurations = document.querySelectorAll('.phase-duration');
    let total = 0;
    
    phaseDurations.forEach(input => {
        total += parseInt(input.value) || 0;
    });
    
    const durationInput = document.getElementById('study-duration');
    if (durationInput) {
        durationInput.value = total;
    }
}

// ============================================================================
// TESTING FUNCTIONS
// ============================================================================

/**
 * Initialize test button event listeners
 */
function initializeTestButtons() {
    const runTestsBtn = document.getElementById('run-tests-btn');
    const healthCheckBtn = document.getElementById('check-health-btn');
    
    if (runTestsBtn) {
        runTestsBtn.addEventListener('click', runAllTests);
    }
    
    if (healthCheckBtn) {
        healthCheckBtn.addEventListener('click', checkHealth);
    }
}

/**
 * Run all drug assessment tests
 */
async function runAllTests() {
    const resultsDiv = document.getElementById('test-results');
    const runTestsBtn = document.getElementById('run-tests-btn');
    
    if (!resultsDiv) return;
    
    // Show loading state
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
        <div style="text-align: center; padding: 20px; background: white; border-radius: 8px; border: 2px solid #3b82f6;">
            <div style="font-size: 32px; margin-bottom: 12px;">🔄</div>
            <h3 style="margin: 0 0 8px 0; color: #1e40af;">Running Tests...</h3>
            <p style="margin: 0; color: #666; font-size: 14px;">Testing all drug assessment endpoints</p>
        </div>
    `;
    
    try {
        setButtonLoading(runTestsBtn, true);
        
        // Call test endpoint
        const response = await fetch('/test-assessment', {
            method: 'GET'
        });
        
        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Display results
        displayTestResults(data);
        
        if (data.summary.failed === 0) {
            showToast('✅ All tests passed!', 'success');
        } else {
            showToast(`⚠️ ${data.summary.failed} test(s) failed`, 'warning');
        }
        
    } catch (error) {
        console.error('Test error:', error);
        resultsDiv.innerHTML = `
            <div style="background: #fee2e2; border: 2px solid #dc2626; padding: 20px; border-radius: 8px;">
                <h3 style="margin: 0 0 8px 0; color: #991b1b;">❌ Test Error</h3>
                <p style="margin: 0; font-size: 14px; color: #991b1b;">${escapeHtml(error.message)}</p>
            </div>
        `;
        showToast('❌ Tests failed to run', 'error');
    } finally {
        setButtonLoading(runTestsBtn, false);
    }
}

/**
 * Display test results in UI
 */
function displayTestResults(data) {
    const resultsDiv = document.getElementById('test-results');
    
    const passedCount = data.summary.passed;
    const failedCount = data.summary.failed;
    const totalCount = data.summary.total;
    const allPassed = failedCount === 0;
    
    let html = `
        <div style="background: white; border: 2px solid ${allPassed ? '#10b981' : '#f59e0b'}; border-radius: 8px; padding: 20px;">
            
            <!-- Summary Header -->
            <div style="text-align: center; padding: 16px; background: ${allPassed ? '#d1fae5' : '#fef3c7'}; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 8px 0; color: ${allPassed ? '#065f46' : '#92400e'}; font-size: 20px;">
                    ${allPassed ? '✅ All Tests Passed!' : '⚠️ Some Tests Failed'}
                </h3>
                <p style="margin: 0; font-size: 16px; color: ${allPassed ? '#065f46' : '#92400e'};">
                    <strong>${passedCount}/${totalCount}</strong> tests passed (${data.summary.success_rate})
                </p>
            </div>
            
            <!-- Individual Test Results -->
            <div style="display: grid; gap: 12px;">
    `;
    
    data.tests.forEach((test, index) => {
        const isPassed = test.status === 'passed';
        const icon = isPassed ? '✅' : '❌';
        const color = isPassed ? '#10b981' : '#dc2626';
        const bgColor = isPassed ? '#d1fae5' : '#fee2e2';
        
        html += `
            <div style="background: ${bgColor}; border: 2px solid ${color}; border-radius: 6px; padding: 12px;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                    <span style="font-size: 20px;">${icon}</span>
                    <strong style="color: ${color}; flex: 1;">${escapeHtml(test.name)}</strong>
                    <span style="font-size: 12px; color: ${color}; text-transform: uppercase; font-weight: bold;">
                        ${test.status}
                    </span>
                </div>
                <p style="margin: 4px 0 0 28px; font-size: 13px; color: #666;">
                    <strong>Endpoint:</strong> ${escapeHtml(test.endpoint)}
                </p>
                ${test.error ? `
                    <p style="margin: 4px 0 0 28px; font-size: 13px; color: ${color};">
                        <strong>Error:</strong> ${escapeHtml(test.error)}
                    </p>
                ` : ''}
            </div>
        `;
    });
    
    html += `
            </div>
            
            <!-- Timestamp -->
            <p style="margin: 16px 0 0 0; text-align: center; font-size: 12px; color: #999;">
                Test run: ${new Date(data.timestamp).toLocaleString()}
            </p>
        </div>
    `;
    
    resultsDiv.innerHTML = html;
}

/**
 * Check system health
 */
async function checkHealth() {
    const resultsDiv = document.getElementById('test-results');
    const healthBtn = document.getElementById('check-health-btn');
    
    if (!resultsDiv) return;
    
    // Show loading
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
        <div style="text-align: center; padding: 20px; background: white; border-radius: 8px; border: 2px solid #10b981;">
            <div style="font-size: 32px; margin-bottom: 12px;">🔄</div>
            <h3 style="margin: 0; color: #065f46;">Checking System Health...</h3>
        </div>
    `;
    
    try {
        setButtonLoading(healthBtn, true);
        
        const response = await fetch('/health');
        
        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Display health status
        displayHealthStatus(data);
        showToast('✅ System is healthy!', 'success');
        
    } catch (error) {
        console.error('Health check error:', error);
        resultsDiv.innerHTML = `
            <div style="background: #fee2e2; border: 2px solid #dc2626; padding: 20px; border-radius: 8px;">
                <h3 style="margin: 0 0 8px 0; color: #991b1b;">❌ Health Check Failed</h3>
                <p style="margin: 0; font-size: 14px; color: #991b1b;">${escapeHtml(error.message)}</p>
            </div>
        `;
        showToast('❌ Health check failed', 'error');
    } finally {
        setButtonLoading(healthBtn, false);
    }
}

/**
 * Display health status
 */
function displayHealthStatus(data) {
    const resultsDiv = document.getElementById('test-results');
    
    const isHealthy = data.status === 'healthy';
    
    let html = `
        <div style="background: white; border: 2px solid #10b981; border-radius: 8px; padding: 20px;">
            
            <!-- Status Header -->
            <div style="text-align: center; padding: 16px; background: #d1fae5; border-radius: 8px; margin-bottom: 20px;">
                <div style="font-size: 48px; margin-bottom: 8px;">💚</div>
                <h3 style="margin: 0 0 8px 0; color: #065f46; font-size: 24px;">System Healthy</h3>
                <p style="margin: 0; font-size: 14px; color: #065f46;">
                    All systems operational
                </p>
            </div>
            
            <!-- Features Status -->
            <div style="margin-bottom: 20px;">
                <h4 style="margin: 0 0 12px 0; color: #1e40af;">📦 Features</h4>
                <div style="display: grid; gap: 8px;">
                    ${Object.entries(data.features).map(([feature, available]) => `
                        <div style="display: flex; align-items: center; gap: 8px; padding: 8px; background: ${available ? '#d1fae5' : '#fef3c7'}; border-radius: 4px;">
                            <span style="font-size: 16px;">${available ? '✅' : '⚠️'}</span>
                            <span style="flex: 1; text-transform: capitalize;">${feature.replace(/_/g, ' ')}</span>
                            <span style="font-weight: bold; color: ${available ? '#065f46' : '#92400e'}; font-size: 12px;">
                                ${available ? 'AVAILABLE' : 'NOT AVAILABLE'}
                            </span>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <!-- Available Endpoints -->
            <div>
                <h4 style="margin: 0 0 12px 0; color: #1e40af;">🔌 Available Endpoints</h4>
                <div style="display: grid; gap: 6px;">
                    ${Object.entries(data.endpoints).map(([name, path]) => `
                        <div style="display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: #f3f4f6; border-radius: 4px; font-size: 13px;">
                            <code style="flex: 1; color: #1e40af; font-weight: 600;">${escapeHtml(path)}</code>
                            <span style="color: #666; font-size: 11px;">${name.replace(/_/g, ' ')}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <!-- Timestamp -->
            <p style="margin: 16px 0 0 0; text-align: center; font-size: 12px; color: #999;">
                Checked: ${new Date(data.timestamp).toLocaleString()}
            </p>
        </div>
    `;
    
    resultsDiv.innerHTML = html;
}

// ============================================================================
// ENHANCED PREDICTION - Combines Sample Size + Drug Assessment
// ============================================================================

/**
 * Enhanced prediction that shows BOTH sample sizes AND drug assessment
 * Use this instead of the separate assessDrug() function
 */
async function getEnhancedPredictionsIntegrated() {
    // This function is called by the "Analyze & Get ML-Powered Recommendations" button
    // It will show both sample size recommendations AND drug assessment in one go
    
    const analyzeBtn = document.querySelector('button[onclick*="predict"]') || 
                       document.getElementById('analyze-btn');
    
    if (!analyzeBtn) {
        console.error('Analyze button not found');
        return;
    }
    
    try {
        setButtonLoading(analyzeBtn, true);
        showToast('🔬 Starting comprehensive analysis...', 'info');
        
        // Note: The existing predict() or similar function should handle sample size
        // Here we just add drug assessment ON TOP of existing results
        
        // Wait a bit for existing analysis to complete
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Try to find first treatment group data from the page
        const firstDrugInput = document.querySelector('input[name*="drug"]:not([value="control"]):not([value="saline"])');
        const firstWeightInput = document.querySelector('input[name*="weight"]');
        const firstAgeInput = document.querySelector('input[name*="age"]');
        const firstDoseInput = document.querySelector('input[name*="dose"]');
        const firstRouteSelect = document.querySelector('select[name*="route"]');
        const firstTargetInput = document.querySelector('input[name*="target"]');
        
        if (!firstDrugInput || !firstDrugInput.value) {
            showToast('⚠️ Please enter a drug name in the first group', 'warning');
            return;
        }
        
        const drugName = firstDrugInput.value.trim();
        
        if (drugName.toLowerCase() === 'control' || drugName.toLowerCase() === 'saline') {
            showToast('ℹ️ Sample size analysis complete. No drug assessment for control group.', 'info');
            return;
        }
        
        showToast('🧪 Analyzing drug properties...', 'info');
        
        // Prepare payload
        const payload = {
            drug_name: drugName,
            weight: parseFloat(firstWeightInput?.value) || 25,
            age: parseFloat(firstAgeInput?.value) || 8,
            dose: parseFloat(firstDoseInput?.value) || 10,
            route: firstRouteSelect?.value || 'oral',
            target_organ: firstTargetInput?.value || '',
            condition: firstTargetInput?.value || ''
        };
        
        console.log('Drug assessment payload:', payload);
        
        // Call backend
        const response = await fetch('/predict-complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Server error: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Display drug assessment AFTER sample size results
        displayIntegratedDrugAssessment(data);
        
        showToast('✅ Complete analysis finished!', 'success');
        
    } catch (error) {
        console.error('Enhanced prediction error:', error);
        showToast('❌ Drug assessment failed: ' + error.message, 'error');
    } finally {
        setButtonLoading(analyzeBtn, false);
    }
}

/**
 * Display drug assessment integrated with sample size results
 */
function displayIntegratedDrugAssessment(data) {
    // Find or create container AFTER sample size results
    let resultsDiv = document.getElementById('integrated-drug-assessment');
    
    if (!resultsDiv) {
        resultsDiv = document.createElement('div');
        resultsDiv.id = 'integrated-drug-assessment';
        resultsDiv.style.marginTop = '30px';
        
        // Try to insert after existing results
        const existingResults = document.querySelector('.results-container, #results, [id*="result"]');
        if (existingResults) {
            existingResults.insertAdjacentElement('afterend', resultsDiv);
        } else {
            document.body.appendChild(resultsDiv);
        }
    }
    
    resultsDiv.style.display = 'block';
    
    const tox = data.toxicity || {};
    const eff = data.effectiveness || {};
    const overall = data.overall_assessment || {};
    const therapeuticWindow = data.therapeutic_window || {};
    const mouseParams = data.mouse_parameters || {};
    
    // Generate comprehensive HTML
    resultsDiv.innerHTML = `
        <div style="background: white; border: 3px solid #22c55e; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <!-- Header -->
            <div style="text-align: center; margin-bottom: 24px;">
                <h2 style="margin: 0 0 10px 0; color: #15803d; font-size: 24px; display: flex; align-items: center; justify-content: center; gap: 10px;">
                    <span style="font-size: 32px;">🔬</span>
                    <span>Advanced Drug Assessment</span>
                </h2>
                <p style="margin: 0; color: #166534; font-size: 14px;">
                    Comprehensive toxicity, efficacy, and pharmacokinetic analysis for ${data.drug_name || 'Unknown Drug'}
                </p>
            </div>
            
            <!-- Mouse Parameters -->
            <div style="background: #dbeafe; border: 2px solid #3b82f6; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 12px 0; color: #1e40af; font-size: 18px;">🐭 Mouse Study Parameters</h3>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
                    <div style="background: white; padding: 10px; border-radius: 6px; text-align: center;">
                        <div style="font-size: 11px; color: #666;">Weight</div>
                        <div style="font-size: 20px; font-weight: bold; color: #1e40af;">${mouseParams.weight_g || 25}g</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 6px; text-align: center;">
                        <div style="font-size: 11px; color: #666;">Age</div>
                        <div style="font-size: 20px; font-weight: bold; color: #1e40af;">${mouseParams.age_weeks || 8}w</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 6px; text-align: center;">
                        <div style="font-size: 11px; color: #666;">Dose</div>
                        <div style="font-size: 20px; font-weight: bold; color: #1e40af;">${mouseParams.dose_mg_kg || 10} mg/kg</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 6px; text-align: center;">
                        <div style="font-size: 11px; color: #666;">Route</div>
                        <div style="font-size: 20px; font-weight: bold; color: #1e40af;">${(mouseParams.route || 'Oral').toUpperCase()}</div>
                    </div>
                </div>
            </div>
            
            ${therapeuticWindow.therapeutic_index ? `
                <!-- Therapeutic Window -->
                <div style="background: #fef3c7; border: 3px solid #f59e0b; border-radius: 10px; padding: 20px; margin-bottom: 24px;">
                    <h3 style="margin: 0 0 16px 0; color: #92400e;">⚖️ Therapeutic Window Analysis</h3>
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 10px;">
                            <div>
                                <div style="font-size: 11px; color: #666;">Therapeutic Index</div>
                                <div style="font-size: 24px; font-weight: bold; color: #d97706;">${therapeuticWindow.therapeutic_index}</div>
                            </div>
                            <div>
                                <div style="font-size: 11px; color: #666;">Effective Dose (ED50)</div>
                                <div style="font-size: 18px; font-weight: bold; color: #059669;">${therapeuticWindow.estimated_ed50} mg/kg</div>
                            </div>
                            <div>
                                <div style="font-size: 11px; color: #666;">Toxic Dose (TD50)</div>
                                <div style="font-size: 18px; font-weight: bold; color: #dc2626;">${therapeuticWindow.estimated_td50} mg/kg</div>
                            </div>
                        </div>
                        <div style="padding: 10px; background: #fef3c7; border-radius: 4px;">
                            <strong style="color: #92400e;">Assessment:</strong> ${therapeuticWindow.window_assessment || 'N/A'}
                        </div>
                    </div>
                    <div style="background: #dbeafe; padding: 12px; border-radius: 6px;">
                        <strong style="color: #1e40af;">💡 Recommendation:</strong>
                        <p style="margin: 8px 0 0 0; color: #1e40af;">${therapeuticWindow.dose_recommendation || 'N/A'}</p>
                    </div>
                </div>
            ` : ''}
            
            <!-- Two Column Layout -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px;">
                
                <!-- Toxicity Column -->
                ${generateToxicitySection(tox, mouseParams)}
                
                <!-- Efficacy Column -->
                ${generateEfficacySection(eff, mouseParams)}
            </div>
            
            <!-- Study Feasibility -->
            ${data.study_feasibility ? generateFeasibilitySection(data.study_feasibility) : ''}
            
            <!-- Warnings -->
            ${tox.warnings && tox.warnings.length > 0 ? generateWarningsSection(tox.warnings) : ''}
            
            <!-- Recommendations -->
            ${eff.recommendations && eff.recommendations.length > 0 ? generateRecommendationsSection(eff.recommendations) : ''}
        </div>
    `;
    
    // Smooth scroll
    setTimeout(() => {
        resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

// ============================================================================
// EVENT LISTENERS
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Export buttons
    const exportPDFBtn = document.getElementById('export-study-pdf');
    const exportDOCBtn = document.getElementById('export-study-doc');
    const clearBtn = document.getElementById('clear-study-plan');
    
    if (exportPDFBtn) {
        exportPDFBtn.addEventListener('click', exportStudyPlanPDF);
    }
    
    if (exportDOCBtn) {
        exportDOCBtn.addEventListener('click', exportStudyPlanDOC);
    }
    
    if (clearBtn) {
        clearBtn.addEventListener('click', clearStudyPlanForm);
    }
    
    // Auto-calculate total duration when phase durations change
    const phaseDurations = document.querySelectorAll('.phase-duration');
    phaseDurations.forEach(input => {
        input.addEventListener('input', updateTotalDuration);
    });
    
    // Initialize total duration
    updateTotalDuration();
    
    // Initialize drug assessment module
    initializeDrugAssessment();
    
    // Initialize test buttons
    initializeTestButtons();
    
    console.log('✅ Study Plan Generator initialized');
    console.log('✅ Drug Assessment module initialized');
    console.log('✅ Test functions initialized');
});

// ============================================================================
// DRUG ASSESSMENT FUNCTIONS (TOXICITY + EFFICACY PREDICTION)
// ============================================================================

/**
 * Initialize drug assessment button event listener
 */
function initializeDrugAssessment() {
    const assessBtn = document.getElementById('assess-drug-btn');
    if (assessBtn) {
        assessBtn.addEventListener('click', assessDrug);
        console.log('✅ Drug Assessment module initialized');
    }
}

/**
 * Main drug assessment function
 */
async function assessDrug() {
    const drugName = document.getElementById('assess-drug-name')?.value.trim();
    const condition = document.getElementById('assess-condition')?.value.trim();
    
    if (!drugName) {
        showToast('⚠️ Please enter a drug name to assess', 'warning');
        return;
    }
    
    const resultsDiv = document.getElementById('assessment-results');
    const assessBtn = document.getElementById('assess-drug-btn');
    
    if (!resultsDiv) {
        console.error('Assessment results div not found');
        return;
    }
    
    // Show loading state
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
        <div style="text-align: center; padding: 40px; background: white; border-radius: 8px; border: 2px solid #26a65b;">
            <div style="font-size: 48px; margin-bottom: 16px;">🔄</div>
            <h3 style="margin: 0 0 8px 0; color: #26a65b;">Analyzing Drug Properties...</h3>
            <p style="margin: 0; color: #666; font-size: 14px;">
                Fetching molecular structure, predicting toxicity & efficacy with mouse-specific parameters
            </p>
        </div>
    `;
    
    try {
        setButtonLoading(assessBtn, true);
        
        // Extract mouse-specific parameters from the form
        // Try to get from the first group if available
        const firstGroupWeight = document.querySelector('input[name*="weight"]')?.value || 25;
        const firstGroupAge = document.querySelector('input[name*="age"]')?.value || 8;
        const firstGroupDose = document.querySelector('input[name*="dose"]')?.value || 10;
        const firstGroupRoute = document.querySelector('select[name*="route"]')?.value || 'oral';
        const firstGroupTarget = document.querySelector('input[name*="target"]')?.value || condition;
        
        // Prepare request payload with mouse parameters
        const payload = {
            drug_name: drugName,
            route: firstGroupRoute,
            condition: condition || '',
            target_organ: firstGroupTarget || condition || '',
            weight: parseFloat(firstGroupWeight) || 25,
            age: parseFloat(firstGroupAge) || 8,
            dose: parseFloat(firstGroupDose) || 10
        };
        
        console.log('Assessment payload:', payload);
        
        // Call backend API
        const response = await fetch('/predict-complete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Server error: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Display results
        displayAssessmentResults(data);
        
        showToast('✅ Drug assessment complete!', 'success');
        
    } catch (error) {
        console.error('Assessment error:', error);
        
        resultsDiv.innerHTML = `
            <div style="background: #fee2e2; border: 2px solid #fecaca; color: #991b1b; padding: 24px; border-radius: 8px;">
                <h3 style="margin: 0 0 8px 0;">❌ Assessment Failed</h3>
                <p style="margin: 0; font-size: 14px;">${escapeHtml(error.message)}</p>
                <p style="margin: 12px 0 0 0; font-size: 13px; color: #7f1d1d;">
                    Common issues: Drug not found in database, API timeout, or invalid drug name.
                </p>
            </div>
        `;
        
        showToast('❌ Failed to assess drug', 'error');
        
    } finally {
        setButtonLoading(assessBtn, false);
    }
}

/**
 * Display comprehensive assessment results
 * @param {Object} data - Assessment data from backend
 */
function displayAssessmentResults(data) {
    const resultsDiv = document.getElementById('assessment-results');
    
    if (!data || !data.toxicity || !data.effectiveness) {
        resultsDiv.innerHTML = `
            <div style="background: #fee2e2; border: 2px solid #dc2626; padding: 20px; border-radius: 8px;">
                <strong>❌ Error:</strong> Invalid assessment data received
            </div>
        `;
        return;
    }
    
    const tox = data.toxicity;
    const eff = data.effectiveness;
    const overall = data.overall_assessment || {};
    const feas = data.study_feasibility || {};
    const mouseParams = data.mouse_parameters || {};
    const therapeuticWindow = data.therapeutic_window || {};
    
    // Build HTML result display
    let html = `
        <div style="background: white; border: 3px solid #26a65b; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <!-- Mouse Parameters Display -->
            <div style="background: linear-gradient(135deg, #e0f2fe 0%, #dbeafe 100%); border: 2px solid #3b82f6; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 12px 0; color: #1e40af; font-size: 18px;">🐭 Mouse Study Parameters</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px;">
                    <div style="background: white; padding: 10px; border-radius: 6px;">
                        <div style="font-size: 11px; color: #666; text-transform: uppercase;">Weight</div>
                        <div style="font-size: 20px; font-weight: bold; color: #1e40af;">${mouseParams.weight_g || 25}g</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 6px;">
                        <div style="font-size: 11px; color: #666; text-transform: uppercase;">Age</div>
                        <div style="font-size: 20px; font-weight: bold; color: #1e40af;">${mouseParams.age_weeks || 8}w</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 6px;">
                        <div style="font-size: 11px; color: #666; text-transform: uppercase;">Dose</div>
                        <div style="font-size: 20px; font-weight: bold; color: #1e40af;">${mouseParams.dose_mg_kg || 10} mg/kg</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 6px;">
                        <div style="font-size: 11px; color: #666; text-transform: uppercase;">Route</div>
                        <div style="font-size: 20px; font-weight: bold; color: #1e40af;">${escapeHtml(mouseParams.route || 'Oral').toUpperCase()}</div>
                    </div>
                </div>
            </div>
            
            <!-- Overall Rating Banner -->
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border-radius: 8px; margin-bottom: 24px; border: 2px solid #26a65b;">
                <h2 style="margin: 0 0 12px 0; color: #155724; font-size: 24px;">${escapeHtml(overall.rating || 'Assessment Complete')}</h2>
                <p style="margin: 0 0 8px 0; color: #155724; font-size: 16px; font-weight: 600;">${escapeHtml(overall.recommendation || '')}</p>
                <div style="display: inline-block; background: white; padding: 8px 16px; border-radius: 6px; margin-top: 8px;">
                    <strong style="color: #155724;">Risk/Benefit Ratio:</strong> 
                    <span style="color: #26a65b; font-size: 18px; font-weight: bold;">${overall.risk_benefit_ratio?.ratio || 'N/A'}</span>
                </div>
                <p style="margin: 8px 0 0 0; font-size: 13px; color: #155724;">
                    ${escapeHtml(overall.risk_benefit_ratio?.assessment || '')}
                </p>
            </div>
            
            <!-- Therapeutic Window Section -->
            ${therapeuticWindow.therapeutic_index ? `
                <div style="background: #fef3c7; border: 3px solid #f59e0b; border-radius: 10px; padding: 20px; margin-bottom: 24px;">
                    <h3 style="margin: 0 0 16px 0; color: #92400e; display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 24px;">⚖️</span>
                        <span>Therapeutic Window Analysis</span>
                    </h3>
                    
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                        <p style="margin: 0 0 8px 0;"><strong>Therapeutic Index:</strong> <span style="color: #d97706; font-size: 20px; font-weight: bold;">${therapeuticWindow.therapeutic_index}</span></p>
                        <p style="margin: 0 0 8px 0;"><strong>Window Class:</strong> <span style="text-transform: uppercase; font-weight: bold;">${escapeHtml(therapeuticWindow.window_class || 'N/A')}</span></p>
                        <p style="margin: 0;"><strong>Assessment:</strong> ${escapeHtml(therapeuticWindow.window_assessment || '')}</p>
                    </div>
                    
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                        <h4 style="margin: 0 0 8px 0; color: #92400e; font-size: 14px;">Dose Parameters:</h4>
                        <p style="margin: 0 0 6px 0;"><strong>Effective Dose (ED50):</strong> ${therapeuticWindow.estimated_ed50} mg/kg</p>
                        <p style="margin: 0 0 6px 0;"><strong>Toxic Dose (TD50):</strong> ${therapeuticWindow.estimated_td50} mg/kg</p>
                        <p style="margin: 0 0 6px 0;"><strong>Safety Margin:</strong> ${therapeuticWindow.safety_margin}x</p>
                        <p style="margin: 0;"><strong>Efficacy at Current Dose:</strong> ${therapeuticWindow.efficacy_at_current_dose}%</p>
                    </div>
                    
                    <div style="background: #dbeafe; padding: 12px; border-radius: 6px; border-left: 4px solid #3b82f6;">
                        <p style="margin: 0; font-weight: bold; color: #1e40af;">💡 ${escapeHtml(therapeuticWindow.dose_recommendation || '')}</p>
                    </div>
                </div>
            ` : ''}
            
            <!-- Two Column Layout: Toxicity + Efficacy -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px;">
                
                <!-- Toxicity Section -->`
    
    // Continue building the rest of the display (keep existing toxicity/efficacy sections)
    html += generateToxicitySection(tox, mouseParams);
    html += generateEfficacySection(eff, mouseParams);
    
    html += `
            </div>
            
            <!-- Study Feasibility -->
            ${generateFeasibilitySection(feas)}
            
            <!-- Warnings Section -->
            ${tox.warnings && tox.warnings.length > 0 ? generateWarningsSection(tox.warnings) : ''}
            
            <!-- Recommendations Section -->
            ${eff.recommendations && eff.recommendations.length > 0 ? generateRecommendationsSection(eff.recommendations) : ''}
            
        </div>
    `;
    
    resultsDiv.innerHTML = html;
    
    // Smooth scroll to results
    setTimeout(() => {
        resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 100);
}

// Helper function to generate toxicity section
function generateToxicitySection(tox, mouseParams) {
    const doseAdjusted = tox.dose_adjusted_toxicity || {};
    const riskScore = tox.overall_risk_score || 50;
    const riskInterpretation = tox.risk_interpretation || '';
    
    return `
                <div style="background: #fff3cd; border: 3px solid #ffc107; border-radius: 10px; padding: 20px;">
                    <h3 style="margin: 0 0 16px 0; color: #856404; display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 24px;">⚠️</span>
                        <span>Toxicity Assessment</span>
                    </h3>
                    
                    <!-- Risk Score Bar -->
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                        <p style="margin: 0 0 8px 0;"><strong>Overall Risk Score:</strong></p>
                        <div style="background: #f3f4f6; height: 30px; border-radius: 15px; overflow: hidden; position: relative;">
                            <div style="background: linear-gradient(90deg, #10b981 0%, #f59e0b 50%, #ef4444 100%); height: 100%; width: ${riskScore}%; transition: width 0.5s;"></div>
                            <span style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: bold; font-size: 14px; color: #1f2937;">${riskScore}/100</span>
                        </div>
                        <p style="margin: 8px 0 0 0; font-size: 13px; color: #856404;">${escapeHtml(riskInterpretation)}</p>
                    </div>
                    
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                        <p style="margin: 0 0 8px 0;"><strong>Category:</strong> <span style="color: #d97706; text-transform: uppercase; font-weight: bold;">${escapeHtml(tox.toxicity_category || 'Unknown')}</span></p>
                        <p style="margin: 0 0 8px 0;"><strong>Confidence:</strong> <span style="color: #26a65b; font-weight: bold;">${tox.confidence || 0}%</span></p>
                        <p style="margin: 0;"><strong>LD50 Range:</strong> ${tox.ld50_range ? `${tox.ld50_range[0]}-${tox.ld50_range[1]} mg/kg` : 'N/A'}</p>
                    </div>
                    
                    ${doseAdjusted.safety_margin ? `
                    <div style="background: ${doseAdjusted.dose_is_safe ? '#d1fae5' : '#fee2e2'}; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                        <p style="margin: 0 0 8px 0;"><strong>Dose Safety Analysis:</strong></p>
                        <p style="margin: 0 0 6px 0;">Safety Margin: <strong>${doseAdjusted.safety_margin}x</strong></p>
                        <p style="margin: 0 0 6px 0;">% of LD50: <strong>${doseAdjusted.percentage_of_ld50}%</strong></p>
                        <p style="margin: 0;">Status: <strong style="text-transform: uppercase;">${escapeHtml(doseAdjusted.safety_class || '')}</strong></p>
                    </div>
                    ` : ''}
                    
                    <h4 style="margin: 16px 0 8px 0; color: #856404; font-size: 14px;">Organ-Specific Risks:</h4>
                    <ul style="margin: 0 0 16px 0; padding-left: 20px; font-size: 13px;">
                        ${generateOrganRisksList(tox.organ_toxicity)}
                    </ul>
                    
                    <h4 style="margin: 16px 0 8px 0; color: #856404; font-size: 14px;">Safe Dosing Guidelines:</h4>
                    <div style="background: white; padding: 10px; border-radius: 6px; font-size: 13px;">
                        <p style="margin: 0 0 6px 0;"><strong>Starting Dose:</strong> ${escapeHtml(tox.dose_recommendations?.starting_dose || 'N/A')}</p>
                        <p style="margin: 0 0 6px 0;"><strong>Maximum Dose:</strong> ${escapeHtml(tox.dose_recommendations?.max_dose || 'N/A')}</p>
                        <p style="margin: 0;"><strong>Escalation:</strong> ${escapeHtml(tox.dose_recommendations?.escalation || 'N/A')}</p>
                    </div>
                </div>
    `;
}

// Helper function to generate efficacy section
function generateEfficacySection(eff, mouseParams) {
    const adjustedEff = eff.adjusted_efficacy || {};
    const pkFactors = eff.pk_factors || {};
    const expectedOutcomes = eff.expected_outcomes || {};
    
    return `
                <div style="background: #d1f2eb; border: 3px solid #26a65b; border-radius: 10px; padding: 20px;">
                    <h3 style="margin: 0 0 16px 0; color: #155724; display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 24px;">✨</span>
                        <span>Efficacy Assessment</span>
                    </h3>
                    
                    <!-- Efficacy Score Bar -->
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                        <p style="margin: 0 0 8px 0;"><strong>Efficacy Score:</strong></p>
                        <div style="background: #f3f4f6; height: 30px; border-radius: 15px; overflow: hidden; position: relative;">
                            <div style="background: linear-gradient(90deg, #26a65b 0%, #10b981 100%); height: 100%; width: ${adjustedEff.efficacy_score || 50}%; transition: width 0.5s;"></div>
                            <span style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: bold; font-size: 14px; color: #1f2937;">${adjustedEff.efficacy_score || 50}/100</span>
                        </div>
                        <p style="margin: 8px 0 0 0; font-size: 13px; color: #155724;">Success Probability: <strong>${adjustedEff.success_probability || 50}%</strong></p>
                    </div>
                    
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-bottom: 12px;">
                        <p style="margin: 0 0 8px 0;"><strong>Prediction:</strong> <span style="color: #26a65b; text-transform: uppercase; font-weight: bold;">${escapeHtml(eff.efficacy_prediction || 'Unknown')}</span></p>
                        <p style="margin: 0 0 8px 0;"><strong>Adjusted Category:</strong> <span style="text-transform: uppercase; font-weight: bold;">${escapeHtml(adjustedEff.efficacy_category || 'N/A')}</span></p>
                        <p style="margin: 0 0 8px 0;"><strong>Confidence:</strong> <span style="color: #26a65b; font-weight: bold;">${eff.confidence || 0}%</span></p>
                        ${eff.median_potency_nM ? `<p style="margin: 0;"><strong>Potency:</strong> ${eff.median_potency_nM.toFixed(1)} nM</p>` : ''}
                    </div>
                    
                    ${pkFactors.estimated_half_life_hours ? `
                    <div style="background: #e0f2fe; padding: 12px; border-radius: 6px; margin-bottom: 12px; border-left: 4px solid #3b82f6;">
                        <h4 style="margin: 0 0 8px 0; color: #1e40af; font-size: 14px;">💊 Pharmacokinetics:</h4>
                        <p style="margin: 0 0 6px 0; font-size: 13px;"><strong>Half-life:</strong> ${pkFactors.estimated_half_life_hours} hours</p>
                        <p style="margin: 0 0 6px 0; font-size: 13px;"><strong>Dosing:</strong> ${escapeHtml(pkFactors.recommended_dosing || '')}</p>
                        <p style="margin: 0; font-size: 13px;"><strong>Steady State:</strong> ${pkFactors.steady_state_days} days</p>
                    </div>
                    ` : ''}
                    
                    <h4 style="margin: 16px 0 8px 0; color: #155724; font-size: 14px;">Expected Outcomes:</h4>
                    <div style="background: white; padding: 10px; border-radius: 6px; font-size: 13px;">
                        <p style="margin: 0 0 6px 0;"><strong>Time to Effect:</strong> ${escapeHtml(expectedOutcomes.time_to_effect || 'N/A')}</p>
                        <p style="margin: 0 0 6px 0;"><strong>Peak Effect:</strong> ${escapeHtml(expectedOutcomes.peak_effect || 'N/A')}</p>
                        <p style="margin: 0 0 6px 0;"><strong>Duration:</strong> ${escapeHtml(expectedOutcomes.duration_of_action || 'N/A')}</p>
                        <p style="margin: 0;"><strong>Effect Magnitude:</strong> <span style="text-transform: uppercase;">${escapeHtml(expectedOutcomes.effect_magnitude || 'N/A')}</span></p>
                    </div>
                    
                    <h4 style="margin: 16px 0 8px 0; color: #155724; font-size: 14px;">Literature Evidence:</h4>
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 13px;">
                        <p style="margin: 0 0 6px 0;"><strong>Papers Found:</strong> ${eff.literature_data?.total_papers || 0}</p>
                        <p style="margin: 0 0 6px 0;"><strong>Positive Outcomes:</strong> ${eff.literature_data?.positive_outcomes || 0}</p>
                        <p style="margin: 0;"><strong>Success Rate:</strong> ${eff.literature_data?.success_rate_percent || 'N/A'}%</p>
                    </div>
                </div>
    `;
}

// Helper functions for warnings and recommendations
function generateFeasibilitySection(feas) {
    return `
            <div style="background: ${feas.recommended ? '#d1fae5' : '#fee2e2'}; border: 3px solid ${feas.recommended ? '#26a65b' : '#dc2626'}; border-radius: 10px; padding: 20px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 16px 0; color: ${feas.recommended ? '#155724' : '#991b1b'}; font-size: 20px;">
                    🎯 Study Recommendation: ${feas.recommended ? '✅ PROCEED WITH STUDY' : '❌ DO NOT PROCEED'}
                </h3>
                
                ${feas.concerns && feas.concerns.length > 0 ? `
                    <div style="margin-bottom: 16px;">
                        <h4 style="margin: 0 0 8px 0; color: ${feas.recommended ? '#155724' : '#991b1b'}; font-size: 14px;">⚠️ Concerns:</h4>
                        <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: ${feas.recommended ? '#155724' : '#991b1b'};">
                            ${feas.concerns.map(c => `<li>${escapeHtml(c)}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
                
                ${feas.modifications && feas.modifications.length > 0 ? `
                    <div style="margin-bottom: 16px;">
                        <h4 style="margin: 0 0 8px 0; color: ${feas.recommended ? '#155724' : '#991b1b'}; font-size: 14px;">💡 Recommended Modifications:</h4>
                        <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: ${feas.recommended ? '#155724' : '#991b1b'};">
                            ${feas.modifications.map(m => `<li>${escapeHtml(m)}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
                
                <div style="text-align: center; padding: 16px; background: ${feas.recommended ? '#c3e6cb' : '#f8d7da'}; border-radius: 8px; margin-top: 16px;">
                    <div style="font-size: 48px; margin-bottom: 8px;">🐭</div>
                    <h4 style="margin: 0 0 8px 0; font-size: 24px; color: ${feas.recommended ? '#155724' : '#721c24'};">
                        Animals Saved: <span style="font-weight: bold;">${feas.animals_saved || 0}</span>
                    </h4>
                    <p style="margin: 0; font-size: 13px; color: ${feas.recommended ? '#155724' : '#721c24'};">
                        ${feas.recommended ? 
                            'Optimized study design reduces unnecessary animal use through better planning' : 
                            'Study not justified based on risk/benefit analysis - all animals saved by not proceeding'}
                    </p>
                </div>
            </div>
    `;
}

function generateWarningsSection(warnings) {
    return `
            <div style="background: #fff3cd; border-left: 6px solid #ffc107; padding: 16px; border-radius: 4px;">
                <h4 style="margin: 0 0 12px 0; color: #856404; font-size: 16px;">⚠️ Important Warnings:</h4>
                <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #856404;">
                    ${warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
                </ul>
            </div>
    `;
}

function generateRecommendationsSection(recommendations) {
    return `
            <div style="background: #d1f2eb; border-left: 6px solid #26a65b; padding: 16px; border-radius: 4px; margin-top: 16px;">
                <h4 style="margin: 0 0 12px 0; color: #155724; font-size: 16px;">💡 Recommendations:</h4>
                <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #155724;">
                    ${recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
                </ul>
            </div>
    `;
}

/**
 * Generate HTML list for organ toxicity risks
 * @param {Object} organToxicity - Organ toxicity data
 * @returns {string} HTML string
 */
function generateOrganRisksList(organToxicity) {
    if (!organToxicity || Object.keys(organToxicity).length === 0) {
        return '<li>No specific organ risks identified</li>';
    }
    
    const riskColors = {
        'high': '#dc2626',
        'moderate': '#d97706',
        'low': '#26a65b'
    };
    
    return Object.entries(organToxicity)
        .map(([organ, risk]) => {
            const color = riskColors[risk.toLowerCase()] || '#666';
            const icon = risk.toLowerCase() === 'high' ? '🔴' : 
                        risk.toLowerCase() === 'moderate' ? '🟡' : '🟢';
            return `<li>${icon} <strong style="text-transform: capitalize;">${escapeHtml(organ)}:</strong> <span style="color: ${color}; font-weight: bold; text-transform: uppercase;">${escapeHtml(risk)}</span></li>`;
        })
        .join('');
}

/**
 * Escape HTML to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// ============================================================================
// KEYBOARD SHORTCUTS
// ============================================================================

document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + S = Export PDF
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        exportStudyPlanPDF();
    }
    
    // Ctrl/Cmd + D = Export Word
    if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
        e.preventDefault();
        exportStudyPlanDOC();
    }
    
    // Ctrl/Cmd + A = Assess Drug (if in assessment section)
    if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        const assessInput = document.getElementById('assess-drug-name');
        if (assessInput && document.activeElement === assessInput) {
            // Allow default select all
        } else if (assessInput) {
            e.preventDefault();
            assessDrug();
        }
    }
});
