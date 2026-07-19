# 🔗 Integration Instructions: Drug Assessment + Sample Size Analysis

## Goal
Make the "Analyze & Get ML-Powered Recommendations" button show BOTH:
1. Sample size recommendations (existing functionality)
2. Drug assessment with toxicity, efficacy, and PK analysis (new functionality)

---

## ✅ Step 1: Modify Your JavaScript (staticjsapp.js)

Add this new enhanced function that combines both analyses. Add it AFTER the existing utility functions:

```javascript
// ============================================================================
// ENHANCED PREDICTION - Combines Sample Size + Drug Assessment
// ============================================================================

/**
 * Enhanced prediction function that gets both sample size AND drug assessment
 */
async function getEnhancedPredictions() {
    const analyzeBtn = document.querySelector('button[onclick*="predict"]') || 
                       document.querySelector('.analyze-button') ||
                       document.getElementById('analyze-btn');
    
    if (!analyzeBtn) {
        console.error('Analyze button not found');
        return;
    }
    
    try {
        setButtonLoading(analyzeBtn, true);
        
        // Collect study groups data
        const groups = collectAllGroups(); // You need this function
        
        if (!groups || groups.length === 0) {
            showToast('⚠️ Please add at least one study group', 'warning');
            return;
        }
        
        // ===== PART 1: Get Sample Size Recommendations =====
        showToast('📊 Analyzing sample sizes...', 'info');
        
        const sampleSizeResponse = await fetch('/predict', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ groups: groups })
        });
        
        if (!sampleSizeResponse.ok) {
            throw new Error('Sample size prediction failed');
        }
        
        const sampleSizeResults = await sampleSizeResponse.json();
        
        // Display sample size results first
        displaySampleSizeResults(sampleSizeResults);
        
        // ===== PART 2: Get Drug Assessment for Each Group =====
        showToast('🔬 Analyzing drug properties...', 'info');
        
        const drugAssessments = [];
        
        for (const group of groups) {
            const drugName = group.drug_name || group.drug;
            
            if (!drugName || drugName.toLowerCase() === 'control' || 
                drugName.toLowerCase() === 'saline') {
                continue; // Skip control groups
            }
            
            try {
                const assessmentResponse = await fetch('/predict-complete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drug_name: drugName,
                        weight: parseFloat(group.weight) || 25,
                        age: parseFloat(group.age) || 8,
                        dose: parseFloat(group.dose) || 10,
                        route: group.route || 'oral',
                        target_organ: group.target_organ || '',
                        condition: group.target_organ || ''
                    })
                });
                
                if (assessmentResponse.ok) {
                    const assessment = await assessmentResponse.json();
                    drugAssessments.push({
                        group_name: group.group_name || drugName,
                        ...assessment
                    });
                }
            } catch (err) {
                console.error(`Drug assessment failed for ${drugName}:`, err);
            }
        }
        
        // Display drug assessments
        if (drugAssessments.length > 0) {
            displayDrugAssessments(drugAssessments);
            showToast('✅ Complete analysis finished!', 'success');
        } else {
            showToast('✅ Sample size analysis complete!', 'success');
        }
        
    } catch (error) {
        console.error('Enhanced prediction error:', error);
        showToast('❌ Analysis failed: ' + error.message, 'error');
    } finally {
        setButtonLoading(analyzeBtn, false);
    }
}

/**
 * Collect all study groups from the form
 */
function collectAllGroups() {
    const groups = [];
    
    // Adjust these selectors based on your actual HTML structure
    const groupContainers = document.querySelectorAll('.group-card, .treatment-group, [data-group]');
    
    groupContainers.forEach((container, index) => {
        const group = {
            group_name: container.querySelector('[name*="group-name"], [name*="groupName"]')?.value || `Group ${index + 1}`,
            drug_name: container.querySelector('[name*="drug"], [name*="treatment"]')?.value || '',
            dose: container.querySelector('[name*="dose"]')?.value || '10',
            weight: container.querySelector('[name*="weight"]')?.value || '25',
            age: container.querySelector('[name*="age"]')?.value || '8',
            route: container.querySelector('[name*="route"]')?.value || 'oral',
            strain: container.querySelector('[name*="strain"]')?.value || '',
            sex: container.querySelector('[name*="sex"]')?.value || '',
            target_organ: container.querySelector('[name*="target"]')?.value || '',
            num_mice: container.querySelector('[name*="mice"], [name*="animals"]')?.value || '',
            sample_types: Array.from(container.querySelectorAll('[name*="sample"]:checked')).map(cb => cb.value)
        };
        
        groups.push(group);
    });
    
    return groups;
}

/**
 * Display sample size results (existing functionality)
 */
function displaySampleSizeResults(results) {
    // Create or find results container
    let resultsDiv = document.getElementById('sample-size-results');
    
    if (!resultsDiv) {
        resultsDiv = document.createElement('div');
        resultsDiv.id = 'sample-size-results';
        resultsDiv.style.marginTop = '30px';
        
        // Insert after the analyze button
        const analyzeBtn = document.querySelector('button[onclick*="predict"]');
        if (analyzeBtn && analyzeBtn.parentElement) {
            analyzeBtn.parentElement.insertAdjacentElement('afterend', resultsDiv);
        } else {
            document.body.appendChild(resultsDiv);
        }
    }
    
    resultsDiv.innerHTML = ''; // Clear previous results
    
    // Build HTML for sample size results
    let html = `
        <div style="background: white; border: 3px solid #3b82f6; border-radius: 12px; padding: 24px; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h2 style="margin: 0 0 20px 0; color: #1e40af; font-size: 24px; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 32px;">📊</span>
                <span>Sample Size Recommendations</span>
            </h2>
    `;
    
    results.forEach((result, index) => {
        const groupColor = index % 2 === 0 ? '#f0f9ff' : '#fef3c7';
        const borderColor = index % 2 === 0 ? '#3b82f6' : '#f59e0b';
        
        html += `
            <div style="background: ${groupColor}; border-left: 4px solid ${borderColor}; padding: 20px; margin-bottom: 15px; border-radius: 8px;">
                <h3 style="margin: 0 0 15px 0; color: #1f2937; font-size: 18px;">
                    ${result.group_name || 'Group ' + (index + 1)} - ${result.drug || 'Unknown'}
                </h3>
                
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 15px;">
                    <div style="background: white; padding: 12px; border-radius: 6px;">
                        <div style="font-size: 12px; color: #6b7280; text-transform: uppercase; margin-bottom: 4px;">Recommended</div>
                        <div style="font-size: 20px; font-weight: bold; color: #059669;">${result.recommended_mice || 'N/A'}</div>
                    </div>
                    
                    <div style="background: white; padding: 12px; border-radius: 6px;">
                        <div style="font-size: 12px; color: #6b7280; text-transform: uppercase; margin-bottom: 4px;">Validation Score</div>
                        <div style="font-size: 20px; font-weight: bold; color: #3b82f6;">${result.validation_score || 0}/100</div>
                    </div>
                    
                    <div style="background: white; padding: 12px; border-radius: 6px;">
                        <div style="font-size: 12px; color: #6b7280; text-transform: uppercase; margin-bottom: 4px;">Literature Sources</div>
                        <div style="font-size: 20px; font-weight: bold; color: #7c3aed;">${result.reference_papers?.length || 0} papers</div>
                    </div>
                </div>
                
                ${result.rationale ? `
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-top: 10px;">
                        <strong style="color: #374151;">Rationale:</strong>
                        <p style="margin: 8px 0 0 0; color: #6b7280; font-size: 14px;">${result.rationale}</p>
                    </div>
                ` : ''}
                
                ${result.warnings && result.warnings.length > 0 ? `
                    <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; border-radius: 6px; margin-top: 10px;">
                        <strong style="color: #92400e;">⚠️ Warnings:</strong>
                        <ul style="margin: 8px 0 0 0; padding-left: 20px; color: #92400e; font-size: 13px;">
                            ${result.warnings.map(w => `<li>${w}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
            </div>
        `;
    });
    
    html += `</div>`;
    resultsDiv.innerHTML = html;
    
    // Smooth scroll
    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Display drug assessments for all groups
 */
function displayDrugAssessments(assessments) {
    // Create or find results container
    let resultsDiv = document.getElementById('drug-assessment-results');
    
    if (!resultsDiv) {
        resultsDiv = document.createElement('div');
        resultsDiv.id = 'drug-assessment-results';
        resultsDiv.style.marginTop = '30px';
        
        // Insert after sample size results
        const sampleSizeDiv = document.getElementById('sample-size-results');
        if (sampleSizeDiv) {
            sampleSizeDiv.insertAdjacentElement('afterend', resultsDiv);
        } else {
            document.body.appendChild(resultsDiv);
        }
    }
    
    resultsDiv.innerHTML = ''; // Clear previous
    
    // Header
    let html = `
        <div style="background: white; border: 3px solid #22c55e; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h2 style="margin: 0 0 20px 0; color: #15803d; font-size: 24px; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 32px;">🔬</span>
                <span>Advanced Drug Assessment</span>
            </h2>
    `;
    
    // Display each assessment
    assessments.forEach((data, index) => {
        html += generateComprehensiveAssessment(data, index);
    });
    
    html += `</div>`;
    resultsDiv.innerHTML = html;
    
    // Smooth scroll
    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Generate comprehensive assessment HTML for a single drug
 */
function generateComprehensiveAssessment(data, index) {
    const tox = data.toxicity || {};
    const eff = data.effectiveness || {};
    const therapeuticWindow = data.therapeutic_window || {};
    const mouseParams = data.mouse_parameters || {};
    
    return `
        <div style="margin-bottom: 30px; padding: 20px; background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border-radius: 10px; border: 2px solid #22c55e;">
            
            <h3 style="margin: 0 0 20px 0; color: #15803d; font-size: 20px; border-bottom: 2px solid #22c55e; padding-bottom: 10px;">
                ${data.group_name || 'Group ' + (index + 1)} - ${data.drug_name || 'Unknown Drug'}
            </h3>
            
            <!-- Mouse Parameters -->
            <div style="background: #dbeafe; border: 2px solid #3b82f6; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                <h4 style="margin: 0 0 12px 0; color: #1e40af;">🐭 Mouse Parameters</h4>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;">
                    <div style="background: white; padding: 8px; border-radius: 4px; text-align: center;">
                        <div style="font-size: 11px; color: #6b7280;">Weight</div>
                        <div style="font-size: 18px; font-weight: bold; color: #1e40af;">${mouseParams.weight_g || 25}g</div>
                    </div>
                    <div style="background: white; padding: 8px; border-radius: 4px; text-align: center;">
                        <div style="font-size: 11px; color: #6b7280;">Age</div>
                        <div style="font-size: 18px; font-weight: bold; color: #1e40af;">${mouseParams.age_weeks || 8}w</div>
                    </div>
                    <div style="background: white; padding: 8px; border-radius: 4px; text-align: center;">
                        <div style="font-size: 11px; color: #6b7280;">Dose</div>
                        <div style="font-size: 18px; font-weight: bold; color: #1e40af;">${mouseParams.dose_mg_kg || 10} mg/kg</div>
                    </div>
                    <div style="background: white; padding: 8px; border-radius: 4px; text-align: center;">
                        <div style="font-size: 11px; color: #6b7280;">Route</div>
                        <div style="font-size: 18px; font-weight: bold; color: #1e40af;">${(mouseParams.route || 'Oral').toUpperCase()}</div>
                    </div>
                </div>
            </div>
            
            <!-- Therapeutic Window -->
            ${therapeuticWindow.therapeutic_index ? `
                <div style="background: #fef3c7; border: 2px solid #f59e0b; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                    <h4 style="margin: 0 0 12px 0; color: #92400e;">⚖️ Therapeutic Window</h4>
                    <div style="background: white; padding: 12px; border-radius: 6px;">
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 10px;">
                            <div>
                                <div style="font-size: 11px; color: #6b7280;">Therapeutic Index</div>
                                <div style="font-size: 20px; font-weight: bold; color: #d97706;">${therapeuticWindow.therapeutic_index}</div>
                            </div>
                            <div>
                                <div style="font-size: 11px; color: #6b7280;">ED50</div>
                                <div style="font-size: 16px; font-weight: bold; color: #059669;">${therapeuticWindow.estimated_ed50} mg/kg</div>
                            </div>
                            <div>
                                <div style="font-size: 11px; color: #6b7280;">TD50</div>
                                <div style="font-size: 16px; font-weight: bold; color: #dc2626;">${therapeuticWindow.estimated_td50} mg/kg</div>
                            </div>
                        </div>
                        <div style="font-size: 13px; color: #92400e; font-weight: 600;">
                            ${therapeuticWindow.window_assessment || ''}
                        </div>
                    </div>
                </div>
            ` : ''}
            
            <!-- Two Columns: Toxicity + Efficacy -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                
                <!-- Toxicity -->
                <div style="background: #fff3cd; border: 2px solid #ffc107; border-radius: 8px; padding: 15px;">
                    <h4 style="margin: 0 0 12px 0; color: #856404;">⚠️ Toxicity</h4>
                    
                    <!-- Risk Score Bar -->
                    ${tox.overall_risk_score !== undefined ? `
                        <div style="margin-bottom: 12px;">
                            <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Overall Risk Score</div>
                            <div style="background: #f3f4f6; height: 24px; border-radius: 12px; overflow: hidden; position: relative;">
                                <div style="background: linear-gradient(90deg, #10b981 0%, #f59e0b 50%, #ef4444 100%); height: 100%; width: ${tox.overall_risk_score}%; transition: width 0.5s;"></div>
                                <span style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: bold; font-size: 12px;">${tox.overall_risk_score}/100</span>
                            </div>
                            <div style="font-size: 11px; color: #856404; margin-top: 4px;">${tox.risk_interpretation || ''}</div>
                        </div>
                    ` : ''}
                    
                    <div style="background: white; padding: 10px; border-radius: 6px; font-size: 13px;">
                        <div><strong>Category:</strong> ${tox.toxicity_category || 'N/A'}</div>
                        <div><strong>Confidence:</strong> ${tox.confidence || 0}%</div>
                        ${tox.ld50_range ? `<div><strong>LD50:</strong> ${tox.ld50_range[0]}-${tox.ld50_range[1]} mg/kg</div>` : ''}
                    </div>
                    
                    ${tox.dose_adjusted_toxicity ? `
                        <div style="background: white; padding: 10px; border-radius: 6px; margin-top: 10px; font-size: 13px;">
                            <div><strong>Safety Margin:</strong> ${tox.dose_adjusted_toxicity.safety_margin}x</div>
                            <div><strong>Status:</strong> <span style="text-transform: uppercase;">${tox.dose_adjusted_toxicity.safety_class || ''}</span></div>
                        </div>
                    ` : ''}
                </div>
                
                <!-- Efficacy -->
                <div style="background: #d1f2eb; border: 2px solid #26a65b; border-radius: 8px; padding: 15px;">
                    <h4 style="margin: 0 0 12px 0; color: #155724;">✨ Efficacy</h4>
                    
                    <!-- Efficacy Score Bar -->
                    ${eff.efficacy_score !== undefined ? `
                        <div style="margin-bottom: 12px;">
                            <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Efficacy Score</div>
                            <div style="background: #f3f4f6; height: 24px; border-radius: 12px; overflow: hidden; position: relative;">
                                <div style="background: linear-gradient(90deg, #26a65b 0%, #10b981 100%); height: 100%; width: ${eff.efficacy_score}%; transition: width 0.5s;"></div>
                                <span style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: bold; font-size: 12px;">${eff.efficacy_score}/100</span>
                            </div>
                            <div style="font-size: 11px; color: #155724; margin-top: 4px;">Success: ${eff.adjusted_efficacy?.success_probability || eff.efficacy_score}%</div>
                        </div>
                    ` : ''}
                    
                    <div style="background: white; padding: 10px; border-radius: 6px; font-size: 13px;">
                        <div><strong>Prediction:</strong> ${eff.efficacy_prediction || 'N/A'}</div>
                        <div><strong>Confidence:</strong> ${eff.confidence || 0}%</div>
                        ${eff.median_potency_nM ? `<div><strong>Potency:</strong> ${eff.median_potency_nM.toFixed(1)} nM</div>` : ''}
                    </div>
                    
                    ${eff.pk_factors ? `
                        <div style="background: white; padding: 10px; border-radius: 6px; margin-top: 10px; font-size: 13px;">
                            <strong>💊 Pharmacokinetics:</strong>
                            <div><strong>Half-life:</strong> ${eff.pk_factors.estimated_half_life_hours}h</div>
                            <div><strong>Dosing:</strong> ${eff.pk_factors.recommended_dosing}</div>
                        </div>
                    ` : ''}
                </div>
            </div>
        </div>
    `;
}
```

---

## ✅ Step 2: Replace Your Existing Button Click Handler

Find the button in your HTML that says "Analyze & Get ML-Powered Recommendations" and change its onclick:

### BEFORE:
```html
<button onclick="predict()">Analyze & Get ML-Powered Recommendations</button>
```

### AFTER:
```html
<button onclick="getEnhancedPredictions()">Analyze & Get ML-Powered Recommendations</button>
```

OR if you don't have onclick:

```html
<button id="analyze-btn" class="analyze-button">
    Analyze & Get ML-Powered Recommendations
</button>

<script>
document.getElementById('analyze-btn').addEventListener('click', getEnhancedPredictions);
</script>
```

---

## ✅ Step 3: Test It!

1. **Fill in your study groups** with:
   - Drug names
   - Doses
   - Weights
   - Ages
   - Routes
   - Target organs

2. **Click "Analyze & Get ML-Powered Recommendations"**

3. **You should see TWO sections:**
   - 📊 Sample Size Recommendations (existing)
   - 🔬 Advanced Drug Assessment (new - with risk scores, efficacy, PK analysis, therapeutic window)

---

## 🎨 What You'll See

```
┌─────────────────────────────────────────────────┐
│ Click: Analyze & Get ML-Powered Recommendations│
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 📊 Sample Size Recommendations                  │
│ ┌─────────────────────────────────────────────┐ │
│ │ Control Group                                │ │
│ │ Recommended: Match treatment                 │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ Treatment Group 1 - Lisinopril              │ │
│ │ Recommended: 12-14 mice                      │ │
│ │ Validation: 85/100                           │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 🔬 Advanced Drug Assessment                      │
│ ┌─────────────────────────────────────────────┐ │
│ │ Treatment Group 1 - Lisinopril              │ │
│ │ 🐭 Mouse Parameters: 25g, 8w, 10mg/kg, Oral │ │
│ │ ⚖️  Therapeutic Window: TI=8.5, MODERATE    │ │
│ │ ⚠️  Toxicity: Risk 45/100, MODERATE         │ │
│ │ ✨ Efficacy: Score 75/100, GOOD             │ │
│ │ 💊 PK: Half-life 3.2h, Twice daily          │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

---

## 🔧 Troubleshooting

### Button doesn't work
- Open browser console (F12)
- Check for errors
- Verify `getEnhancedPredictions` function is loaded

### Only shows sample sizes
- Check that drug names are valid (not "control" or "saline")
- Verify Flask server is running
- Check backend logs for errors

### Drug assessment empty
- Make sure groups have `drug_name`, `dose`, `weight`, `age`, `route` filled in
- Try common drugs: Aspirin, Metformin, Lisinopril

---

## 📝 Summary

This integration makes ONE button show EVERYTHING:
✅ Sample size recommendations (statistical power analysis)
✅ Drug toxicity assessment (risk scores, organ risks)
✅ Drug efficacy prediction (success probability)
✅ Pharmacokinetic analysis (half-life, dosing)
✅ Therapeutic window (TI, ED50, TD50)
✅ Mouse-specific predictions (age, weight, route adjustments)

All from clicking ONE button! 🚀
