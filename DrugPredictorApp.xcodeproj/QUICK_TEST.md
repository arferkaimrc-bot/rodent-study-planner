# 🚀 Quick Test Guide - See All Enhanced Features

## ✅ 3-Minute Setup

### Step 1: Verify Backend is Running
Open terminal and run:
```bash
python app.py
```

You should see:
```
Starting Enhanced Rodent Study Planner v3.0
ML features: ✓ ENABLED
APIs configured: PubMed, Semantic Scholar, OpenAlex, CrossRef, Europe PMC, IMPC
Blood calculator: ✓ ACTIVE
```

### Step 2: Test the API Directly
Open a new terminal and test with curl:

```bash
curl -X POST http://localhost:5000/predict-complete \
  -H "Content-Type: application/json" \
  -d '{
    "drug_name": "Aspirin",
    "weight": 25,
    "age": 8,
    "dose": 10,
    "route": "oral",
    "target_organ": "brain",
    "condition": "inflammation"
  }'
```

**Expected Response:**
You should get a JSON response with:
- ✅ `toxicity` → `overall_risk_score`, `dose_adjusted_toxicity`, `organ_toxicity`
- ✅ `effectiveness` → `efficacy_score`, `pk_factors`, `expected_outcomes`
- ✅ `therapeutic_window` → `therapeutic_index`, `estimated_ed50`, `estimated_td50`
- ✅ `mouse_parameters` → `weight_g`, `age_weeks`, `dose_mg_kg`, `route`

---

## 🧪 Test in Browser (Without UI Changes)

### Option 1: Use Browser Console

1. Open your app: http://localhost:5000
2. Press F12 to open Developer Tools
3. Go to **Console** tab
4. Paste this code:

```javascript
// Test the enhanced prediction API
fetch('/predict-complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        drug_name: 'Lisinopril',
        weight: 25,
        age: 8,
        dose: 10,
        route: 'oral',
        target_organ: 'heart',
        condition: 'hypertension'
    })
})
.then(res => res.json())
.then(data => {
    console.log('=== FULL RESPONSE ===');
    console.log(data);
    
    console.log('\n=== MOUSE PARAMETERS ===');
    console.log(data.mouse_parameters);
    
    console.log('\n=== TOXICITY RISK SCORE ===');
    console.log('Score:', data.toxicity.overall_risk_score);
    console.log('Interpretation:', data.toxicity.risk_interpretation);
    console.log('Dose Safety:', data.toxicity.dose_adjusted_toxicity);
    
    console.log('\n=== EFFICACY SCORE ===');
    console.log('Score:', data.effectiveness.efficacy_score);
    console.log('Success Probability:', data.effectiveness.adjusted_efficacy.success_probability);
    console.log('Category:', data.effectiveness.adjusted_efficacy.efficacy_category);
    
    console.log('\n=== PHARMACOKINETICS ===');
    console.log(data.effectiveness.pk_factors);
    
    console.log('\n=== EXPECTED OUTCOMES ===');
    console.log('Time to Effect:', data.effectiveness.expected_outcomes.time_to_effect);
    console.log('Peak Effect:', data.effectiveness.expected_outcomes.peak_effect);
    console.log('Duration:', data.effectiveness.expected_outcomes.duration_of_action);
    
    console.log('\n=== THERAPEUTIC WINDOW ===');
    console.log('Therapeutic Index:', data.therapeutic_window.therapeutic_index);
    console.log('Window Class:', data.therapeutic_window.window_class);
    console.log('ED50:', data.therapeutic_window.estimated_ed50);
    console.log('TD50:', data.therapeutic_window.estimated_td50);
    console.log('Safety Margin:', data.therapeutic_window.safety_margin);
    console.log('Optimal Dose Range:', data.therapeutic_window.optimal_dose_range);
});
```

5. Check the console output - you'll see ALL the enhanced data!

---

## 📊 Sample Test Cases

### Test Case 1: Safe Drug (Aspirin)
```json
{
  "drug_name": "Aspirin",
  "weight": 25,
  "age": 8,
  "dose": 10,
  "route": "oral",
  "target_organ": "inflammation"
}
```

**Expected:**
- Risk Score: 20-40 (LOW RISK)
- Efficacy Score: 60-80 (GOOD)
- Therapeutic Index: >5 (MODERATE or WIDE window)

---

### Test Case 2: High-Risk Drug (Doxorubicin - Chemotherapy)
```json
{
  "drug_name": "Doxorubicin",
  "weight": 25,
  "age": 8,
  "dose": 50,
  "route": "iv",
  "target_organ": "tumor"
}
```

**Expected:**
- Risk Score: 60-80 (HIGH RISK)
- Efficacy Score: 70-90 (GOOD but risky)
- Therapeutic Index: <5 (NARROW window)
- Warnings about high dose + IV route

---

### Test Case 3: Age-Sensitive (Young Mice)
```json
{
  "drug_name": "Metformin",
  "weight": 18,
  "age": 4,
  "dose": 20,
  "route": "oral",
  "target_organ": "liver"
}
```

**Expected:**
- Warnings about young mice (age < 6 weeks)
- Lower efficacy due to immature metabolism
- Safety recommendations

---

### Test Case 4: Old Mice + High Dose
```json
{
  "drug_name": "Ibuprofen",
  "weight": 30,
  "age": 22,
  "dose": 150,
  "route": "oral",
  "target_organ": "kidney"
}
```

**Expected:**
- High risk score (age >18w + high dose)
- Kidney toxicity warnings
- Dose reduction recommendations

---

## 📸 What Each Feature Looks Like

### 1. Mouse Parameters
```json
"mouse_parameters": {
  "weight_g": 25,
  "age_weeks": 8,
  "dose_mg_kg": 10,
  "route": "oral"
}
```

### 2. Overall Risk Score
```json
"toxicity": {
  "overall_risk_score": 45,
  "risk_interpretation": "MODERATE RISK - Enhanced monitoring required"
}
```

### 3. Dose-Adjusted Toxicity
```json
"dose_adjusted_toxicity": {
  "adjusted_category": "moderate",
  "safety_margin": 8.5,
  "safety_class": "safe",
  "dose_is_safe": true,
  "percentage_of_ld50": 4.2
}
```

### 4. Efficacy Score
```json
"adjusted_efficacy": {
  "efficacy_score": 72.5,
  "efficacy_category": "good",
  "success_probability": 72.5,
  "bioavailability_factor": 0.6
}
```

### 5. Pharmacokinetics
```json
"pk_factors": {
  "volume_of_distribution_mL": 62.5,
  "estimated_half_life_hours": 3.2,
  "clearance_factor": 1.0,
  "recommended_dosing": "Twice daily",
  "steady_state_days": 0.7
}
```

### 6. Expected Response Times
```json
"expected_outcomes": {
  "time_to_effect": "5 days",
  "peak_effect": "10 days",
  "duration_of_action": "3 weeks",
  "effect_magnitude": "good"
}
```

### 7. Therapeutic Window
```json
"therapeutic_window": {
  "therapeutic_index": 8.5,
  "window_class": "moderate",
  "window_assessment": "MODERATE therapeutic window - Careful dosing required",
  "estimated_ed50": 5.2,
  "estimated_td50": 44.2,
  "safety_margin": 8.5,
  "efficacy_at_current_dose": 75,
  "optimal_dose_range": {
    "min": 4.16,
    "max": 22.1,
    "recommended": 9.1
  }
}
```

---

## 🔍 Verify All Features Are Working

Run this comprehensive test:

```javascript
async function testAllFeatures() {
    const drugs = ['Aspirin', 'Metformin', 'Lisinopril', 'Doxorubicin'];
    
    for (const drug of drugs) {
        console.log(`\n\n========== TESTING: ${drug} ==========`);
        
        const response = await fetch('/predict-complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                drug_name: drug,
                weight: 25,
                age: 8,
                dose: 10,
                route: 'oral'
            })
        });
        
        const data = await response.json();
        
        // Check for all required fields
        const checks = {
            'Mouse Parameters': !!data.mouse_parameters,
            'Risk Score': !!data.toxicity.overall_risk_score,
            'Risk Interpretation': !!data.toxicity.risk_interpretation,
            'Dose Adjusted Toxicity': !!data.toxicity.dose_adjusted_toxicity,
            'Efficacy Score': !!data.effectiveness.efficacy_score,
            'Adjusted Efficacy': !!data.effectiveness.adjusted_efficacy,
            'PK Factors': !!data.effectiveness.pk_factors,
            'Expected Outcomes': !!data.effectiveness.expected_outcomes,
            'Therapeutic Window': !!data.therapeutic_window,
            'Therapeutic Index': !!data.therapeutic_window.therapeutic_index
        };
        
        console.log('✅ Feature Checks:');
        Object.entries(checks).forEach(([feature, present]) => {
            console.log(`  ${present ? '✅' : '❌'} ${feature}`);
        });
        
        // Display key metrics
        console.log('\n📊 Key Metrics:');
        console.log(`  Risk Score: ${data.toxicity.overall_risk_score}/100`);
        console.log(`  Efficacy Score: ${data.effectiveness.efficacy_score}/100`);
        console.log(`  Therapeutic Index: ${data.therapeutic_window.therapeutic_index}`);
        console.log(`  Safety Margin: ${data.toxicity.dose_adjusted_toxicity.safety_margin}x`);
        console.log(`  Half-life: ${data.effectiveness.pk_factors.estimated_half_life_hours}h`);
    }
    
    console.log('\n\n========== TEST COMPLETE ==========');
}

// Run the test
testAllFeatures();
```

---

## ✅ Success Criteria

You should see:

1. **Risk Score** (0-100) with color-coded interpretation
2. **Efficacy Score** (0-100) with success probability
3. **Pharmacokinetic data** (half-life, dosing frequency, steady state)
4. **Expected response times** (onset, peak, duration)
5. **Therapeutic window** (TI, ED50, TD50, optimal dose range)
6. **Mouse-specific warnings** (age, weight, dose, route)
7. **Organ-specific toxicity risks** (liver, kidney, heart, brain, etc.)

---

## 🐛 Troubleshooting

### "TypeError: Cannot read property 'overall_risk_score' of undefined"
**Fix:** Update your `app.py` - the enhancements are in the Python backend.

### "404 Not Found for /predict-complete"
**Fix:** Make sure Flask server is running and routes are defined.

### "Drug not found in PubChem"
**Try these drugs that definitely exist:**
- Aspirin
- Metformin
- Lisinopril
- Ibuprofen
- Acetaminophen (Paracetamol)
- Atorvastatin

### API returns but missing fields
**Check Flask logs for:**
- RDKit import errors
- Missing dependencies
- API timeout issues

---

## 🎯 Next Steps

Once you confirm the API is working:

1. ✅ Add the HTML section from `drug_assessment_section.html`
2. ✅ Refresh your browser
3. ✅ Fill in study group parameters
4. ✅ Use the "Analyze Drug Properties" button
5. ✅ See all features in beautiful UI!

---

**You're seeing the sample size recommendations. The enhanced drug assessment is a SEPARATE feature that needs to be triggered separately!** 🚀
