"""
Enhanced Experimental Rodent Study Planner - COMPLETE VERSION
=============================================================
Features:
- Multiple scientific paper APIs (NCBI, Semantic Scholar, OpenAlex, CrossRef)
- Machine Learning for sample size prediction
- Blood quantity calculator
- Enhanced PDF/Word exports with diagrams and colors
- Power analysis curves
- Study timeline visualizations

Author: Enhanced Platform v3.0
Version: 3.0
"""

from flask import Flask, request, jsonify, render_template, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from io import BytesIO
import logging
from datetime import datetime, timedelta
import os
import re
import hashlib
import pickle
import numpy as np
import pandas as pd
from functools import lru_cache
from tenacity import retry, stop_after_attempt, wait_exponential
from markupsafe import escape
import time
import json

# PDF / Word generation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.lib.colors import HexColor
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# Statistical packages
from scipy import stats
from statsmodels.stats.power import tt_ind_solve_power

# ML packages
try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split, cross_val_score
    import joblib
    ML_AVAILABLE = True
except ImportError:   
    ML_AVAILABLE = False
    print("Warning: scikit-learn not installed. ML features disabled.")

# Validation
try:
    from marshmallow import Schema, fields, validate, ValidationError, EXCLUDE
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False
    print("Warning: marshmallow not installed. Advanced validation disabled.")

# RDKit for molecular descriptors (REQUIRED for toxicity prediction)
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Crippen, Lipinski, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    logger_msg = "RDKit not installed. Toxicity prediction will use simplified model."
    print(f"Warning: {logger_msg}")

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Application configuration."""
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # API Configuration
    NCBI_API_KEY = os.getenv('NCBI_API_KEY', None)
    NCBI_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    PUBCHEM_API_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    EUROPE_PMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    IMPC_BASE = "https://www.ebi.ac.uk/mi/impc/solr"
    
    # NEW APIS
    SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
    OPENALEX_BASE = "https://api.openalex.org"
    CROSSREF_BASE = "https://api.crossref.org/works"
    
    # ChEMBL API for bioactivity data
    CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
    CHEMBL_TIMEOUT = 15

    # PubChem PUG-View + SDQ (real experimental acute-toxicity / LD50 data from ChemIDplus)
    PUBCHEM_PUGVIEW_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound"
    PUBCHEM_SDQ = "https://pubchem.ncbi.nlm.nih.gov/sdq/sdqagent.cgi"

    # Trained LD50 regression model (real data: TDC LD50_Zhu, rat oral)
    LD50_MODEL_PATH = './ml_models/ld50_model.pkl'
    LD50_META_PATH = './ml_models/ld50_meta.json'
    
    # Toxicity prediction settings
    TOXICITY_CONFIDENCE_THRESHOLD = 60  # Minimum confidence to trust predictions
    EFFICACY_CONFIDENCE_THRESHOLD = 50
    
    # Request settings
    REQUEST_TIMEOUT = 10
    MAX_RETRIES = 3
    
    # Cache settings
    CACHE_DIR = './cache'
    CACHE_EXPIRY_HOURS = 24
    
    # ML settings
    ML_MODEL_PATH = './ml_models'
    ML_TRAINING_DATA_PATH = './training_data'
    
    # Rate limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_DEFAULT = "200 per day"
    RATE_LIMIT_PREDICT = "10 per minute"

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# FLASK APP INITIALIZATION
# ============================================================================

app = Flask(__name__)
app.config.from_object(Config)

# Create necessary directories
os.makedirs(Config.CACHE_DIR, exist_ok=True)
os.makedirs(Config.ML_MODEL_PATH, exist_ok=True)
os.makedirs(Config.ML_TRAINING_DATA_PATH, exist_ok=True)
os.makedirs('./templates', exist_ok=True)
os.makedirs('./static/css', exist_ok=True)
os.makedirs('./static/js', exist_ok=True)

# Rate limiter
if Config.RATE_LIMIT_ENABLED:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[Config.RATE_LIMIT_DEFAULT],
        storage_uri="memory://"
    )
else:
    limiter = None

# ============================================================================
# AUTHENTICATION & ACCESS CONTROL
# ============================================================================
# Email+password login, admin-created accounts, every page behind login.
try:
    from auth import init_auth
    init_auth(app)
    AUTH_ENABLED = True
    logger.info("Authentication enabled (login required)")
except Exception as e:
    AUTH_ENABLED = False
    logger.error(f"Authentication setup failed, app runs WITHOUT login: {e}")

# ============================================================================
# DATA VALIDATION SCHEMAS
# ============================================================================

if VALIDATION_AVAILABLE:
    class GroupSchema(Schema):
        class Meta:
            unknown = EXCLUDE
        
        group_name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
        drug_name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
        dose = fields.Float(validate=validate.Range(min=0, max=10000))
        strain = fields.Str()

        sex = fields.Str(validate=validate.OneOf(['Male', 'Female', 'Mixed']))
        target_organ = fields.Str(validate=validate.Length(max=200))
        num_mice = fields.Integer(required=True, validate=validate.Range(min=1, max=100))
        # Weight range covers both mice (~10-60 g) and rats (~150-600 g).
        weight = fields.Float(validate=validate.Range(min=10, max=600))
        age = fields.Float(validate=validate.Range(min=2, max=104))
        route = fields.Str(validate=validate.OneOf(['Oral', 'IP', 'IV', 'SC', 'IM', 'ICV']))
        diet_type = fields.Str(validate=validate.OneOf(['Standard', 'High fat', 'Fast']))
        start_date = fields.Str()
        sample_types = fields.List(fields.Str())
        blood_quantity = fields.Str()
        # Newer form fields (kept so they pass validation instead of being dropped)
        species = fields.Str(validate=validate.OneOf(['Mouse', 'Rat']))
        experiment_type = fields.Str(validate=validate.Length(max=100))
        toxicity_endpoints = fields.List(fields.Str())
    
    class StudySchema(Schema):
        class Meta:
            unknown = EXCLUDE
        
        study_title = fields.Str(validate=validate.Length(max=500))
        pi_name = fields.Str(validate=validate.Length(max=200))
        groups = fields.List(fields.Nested(GroupSchema), required=True, validate=validate.Length(min=1, max=20))

# ============================================================================
# BLOOD QUANTITY CALCULATOR
# ============================================================================

class BloodQuantityCalculator:
    """Calculate blood quantities needed for various assays."""
    
    # Mouse blood volume: ~70-80 mL/kg (average 75 mL/kg)
    # Safe single collection: 10% of total blood volume
    # Safe repeated collection: 7.5% every 2 weeks
    
    ASSAY_REQUIREMENTS = {
        # Format: (min_volume_ul, optimal_volume_ul, sample_type)
        'Complete Blood Count (CBC)': (50, 100, 'whole blood'),
        'Blood Chemistry Panel': (100, 200, 'serum'),
        'Lipid Profile': (50, 100, 'serum'),
        'Glucose': (5, 10, 'whole blood'),
        'Cytokine Analysis (ELISA)': (50, 100, 'plasma'),
        'Western Blot': (100, 200, 'plasma'),
        'PCR/Gene Expression': (100, 200, 'whole blood'),
        'Flow Cytometry': (50, 100, 'whole blood'),
        'Pharmacokinetics': (25, 50, 'plasma'),
        'Antibody Titers': (50, 100, 'serum'),
        'Coagulation Studies': (200, 300, 'plasma'),
        'Metabolomics': (100, 200, 'plasma'),
        'Proteomics': (200, 300, 'plasma')
    }
    
    @staticmethod
    def calculate_total_blood_volume(weight_g):
        """Calculate total blood volume in mL."""
        weight_kg = weight_g / 1000.0
        return weight_kg * 75  # 75 mL/kg
    
    @staticmethod
    def calculate_safe_collection(weight_g, timepoints=1):
        """Calculate safe collection volume."""
        total_volume = BloodQuantityCalculator.calculate_total_blood_volume(weight_g)
        
        if timepoints == 1:
            # Single collection: 10% of total blood
            safe_volume = total_volume * 0.10
        else:
            # Multiple collections: 7.5% per collection (assuming 2-week intervals)
            safe_volume = total_volume * 0.075
        
        return safe_volume * 1000  # Convert to microliters
    
    @staticmethod
    def calculate_blood_needed(sample_types, weight_g=25, timepoints=1, num_replicates=1):
        """
        Calculate total blood needed for selected sample types.
        
        Args:
            sample_types: List of sample type strings
            weight_g: Mouse weight in grams
            timepoints: Number of blood collection timepoints
            num_replicates: Number of technical replicates per assay
        
        Returns:
            Dictionary with blood requirements and safety assessment
        """
        total_needed = 0
        breakdown = []
        
        # Identify blood-related samples
        blood_samples = [s for s in sample_types if any(keyword in s.lower()
                        for keyword in ['blood', 'plasma', 'serum'])]
        
        if not blood_samples:
            return {
                'needed': False,
                'total_volume_ul': 0,
                'safe_volume_ul': 0,
                'breakdown': [],
                'safety_assessment': 'No blood collection needed'
            }
        
        # Determine which assays to perform based on sample types
        assays_needed = []
        
        for sample in blood_samples:
            sample_lower = sample.lower()
            
            # Map sample types to common assays
            if 'whole blood' in sample_lower:
                assays_needed.extend(['Complete Blood Count (CBC)', 'Flow Cytometry', 'Glucose'])
            if 'plasma' in sample_lower:
                assays_needed.extend(['Cytokine Analysis (ELISA)', 'Pharmacokinetics', 'Metabolomics'])
            if 'serum' in sample_lower:
                assays_needed.extend(['Blood Chemistry Panel', 'Lipid Profile', 'Antibody Titers'])
        
        # Remove duplicates
        assays_needed = list(set(assays_needed))
        
        # Calculate total volume needed
        for assay in assays_needed:
            if assay in BloodQuantityCalculator.ASSAY_REQUIREMENTS:
                min_vol, opt_vol, sample_type = BloodQuantityCalculator.ASSAY_REQUIREMENTS[assay]
                volume_per_replicate = opt_vol
                total_for_assay = volume_per_replicate * num_replicates * timepoints
                
                total_needed += total_for_assay
                breakdown.append({
                    'assay': assay,
                    'volume_per_sample_ul': opt_vol,
                    'replicates': num_replicates,
                    'timepoints': timepoints,
                    'total_ul': total_for_assay,
                    'sample_type': sample_type
                })
        
        # Add 20% overage for pipetting loss
        total_needed_with_overage = total_needed * 1.2
        
        # Calculate safe collection volume
        safe_volume = BloodQuantityCalculator.calculate_safe_collection(weight_g, timepoints)
        total_blood_volume = BloodQuantityCalculator.calculate_total_blood_volume(weight_g)
        
        # Safety assessment
        if total_needed_with_overage <= safe_volume:
            safety = "✓ SAFE - Within recommended limits"
            safety_color = "green"
        elif total_needed_with_overage <= safe_volume * 1.3:
            safety = "⚠ CAUTION - Approaching limits, monitor animals closely"
            safety_color = "orange"
        else:
            safety = "✗ UNSAFE - Exceeds safe collection limits. Reduce assays or increase timepoint intervals"
            safety_color = "red"
        
        return {
            'needed': True,
            'total_volume_ul': round(total_needed_with_overage, 1),
            'total_volume_ml': round(total_needed_with_overage / 1000, 2),
            'safe_volume_ul': round(safe_volume, 1),
            'safe_volume_ml': round(safe_volume / 1000, 2),
            'total_blood_volume_ml': round(total_blood_volume, 2),
            'percentage_of_total': round((total_needed_with_overage / (total_blood_volume * 1000)) * 100, 1),
            'breakdown': breakdown,
            'safety_assessment': safety,
            'safety_color': safety_color,
            'recommendations': [
                f"Total blood volume in mouse: ~{round(total_blood_volume, 1)} mL",
                f"Safe single collection: {round(safe_volume/1000, 2)} mL ({round(safe_volume, 0)} µL)",
                "Allow 2-week recovery between collections for repeated sampling",
                "Monitor animals for signs of anemia (lethargy, pale feet/ears)",
                "Consider terminal collection if volume exceeds safe limits"
            ]
        }

# ============================================================================
# TOXICITY PREDICTION
# ============================================================================

class ToxicityPredictor:
    """
    Predict drug toxicity using molecular descriptors and external databases.
    Integrates with existing caching and logging systems.
    """
    
    def __init__(self):
        self.cache = None  # Will be set after api_cache is initialized
        # Load the real trained LD50 model (TDC LD50_Zhu, rat oral acute toxicity)
        self.ld50_model = None
        self.ld50_meta = None
        try:
            if os.path.exists(Config.LD50_MODEL_PATH):
                self.ld50_model = joblib.load(Config.LD50_MODEL_PATH)
                if os.path.exists(Config.LD50_META_PATH):
                    with open(Config.LD50_META_PATH) as f:
                        self.ld50_meta = json.load(f)
                logger.info("Loaded trained LD50 model (real experimental data)")
            else:
                logger.warning("Trained LD50 model not found; run train_ld50_model.py")
        except Exception as e:
            logger.error(f"Failed to load LD50 model: {e}")
        logger.info("ToxicityPredictor initialized")
    
    def get_chemical_structure(self, drug_name):
        """Fetch SMILES structure from PubChem."""
        cache_key = {'drug': drug_name.lower(), 'type': 'smiles'}
        if self.cache:
            cached = self.cache.get('pubchem_smiles', cache_key)
            if cached:
                return cached
        
        try:
            # Get CID from existing function; propagate its specific error
            # (spelling vs. temporarily-unreachable) instead of masking it.
            cid_data = get_drug_data_from_ncbi(drug_name)
            if not cid_data['success']:
                return {'success': False,
                        'error': cid_data.get('error', 'Drug not found in PubChem')}
            
            cid = cid_data.get('cid')
            if not cid:
                return {'success': False, 'error': 'No CID found'}
            
            # Fetch SMILES. PubChem deprecated 'CanonicalSMILES'; the current
            # fields are 'SMILES' and 'ConnectivitySMILES'. Request all and use
            # whichever is present for backward/forward compatibility.
            url = (f"{Config.PUBCHEM_API_BASE}/compound/cid/{cid}"
                   f"/property/SMILES,ConnectivitySMILES,CanonicalSMILES,IsomericSMILES/JSON")
            response = requests.get(url, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()

            data = response.json()
            props = data['PropertyTable']['Properties'][0]
            smiles = (props.get('SMILES') or props.get('CanonicalSMILES')
                      or props.get('IsomericSMILES') or props.get('ConnectivitySMILES'))
            if not smiles:
                return {'success': False, 'error': 'No SMILES returned by PubChem', 'cid': cid}

            result = {'success': True, 'smiles': smiles, 'cid': cid}
            if self.cache:
                self.cache.set('pubchem_smiles', cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Error fetching SMILES for {drug_name}: {e}")
            return {'success': False, 'error': str(e)}
    
    def calculate_molecular_descriptors(self, smiles):
        """Calculate molecular descriptors using RDKit."""
        if not RDKIT_AVAILABLE:
            logger.warning("RDKit not available, using fallback descriptors")
            return self._fallback_descriptors()
        
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return {'success': False, 'error': 'Invalid SMILES structure'}
            
            descriptors = {
                'molecular_weight': Descriptors.MolWt(mol),
                'logp': Crippen.MolLogP(mol),
                'h_donors': Lipinski.NumHDonors(mol),
                'h_acceptors': Lipinski.NumHAcceptors(mol),
                'rotatable_bonds': Lipinski.NumRotatableBonds(mol),
                'aromatic_rings': Lipinski.NumAromaticRings(mol),
                'tpsa': Descriptors.TPSA(mol)
            }
            
            return {'success': True, 'descriptors': descriptors}
            
        except Exception as e:
            logger.error(f"Error calculating descriptors: {e}")
            return {'success': False, 'error': str(e)}
    
    def _fallback_descriptors(self):
        """Simplified descriptors when RDKit unavailable."""
        return {
            'success': True,
            'descriptors': {
                'molecular_weight': 300,  # Average
                'logp': 2.0,
                'h_donors': 2,
                'h_acceptors': 4,
                'rotatable_bonds': 5,
                'aromatic_rings': 1,
                'tpsa': 75
            },
            'note': 'Using average values - install RDKit for accurate predictions'
        }
    
    # ------------------------------------------------------------------
    # LD50 prediction — HYBRID: real experimental data first, trained ML
    # model second, molecular heuristic only as a last resort.
    # Categories (mg/kg): high (<50), moderate (50-500), low (500-2000),
    # very_low (>2000).
    # ------------------------------------------------------------------

    @staticmethod
    def ld50_mgkg_to_category(ld50_mg_kg):
        """Map an LD50 value in mg/kg to a toxicity category + a tight range."""
        if ld50_mg_kg < 50:
            return 'high', (1, 50)
        elif ld50_mg_kg < 500:
            return 'moderate', (50, 500)
        elif ld50_mg_kg < 2000:
            return 'low', (500, 2000)
        else:
            return 'very_low', (2000, 99999)

    def _featurize_smiles(self, smiles):
        """Build the feature vector used by the trained LD50 model."""
        if not RDKIT_AVAILABLE or not self.ld50_meta:
            return None
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        desc = {
            'molecular_weight': Descriptors.MolWt(mol),
            'logp': Crippen.MolLogP(mol),
            'h_donors': Lipinski.NumHDonors(mol),
            'h_acceptors': Lipinski.NumHAcceptors(mol),
            'rotatable_bonds': Lipinski.NumRotatableBonds(mol),
            'aromatic_rings': Lipinski.NumAromaticRings(mol),
            'tpsa': Descriptors.TPSA(mol),
        }
        desc_vec = [desc[n] for n in self.ld50_meta['descriptor_names']]
        fp = rdMolDescriptors.GetMorganFingerprintAsBitVect(
            mol, radius=self.ld50_meta['fp_radius'], nBits=self.ld50_meta['fp_bits'])
        return [desc_vec + list(fp)], Descriptors.MolWt(mol)

    def predict_ld50_ml(self, smiles):
        """Predict LD50 (mg/kg) with the trained model. Returns dict or None."""
        if self.ld50_model is None:
            return None
        feats = self._featurize_smiles(smiles)
        if feats is None:
            return None
        X, mw = feats
        try:
            y = float(self.ld50_model.predict(X)[0])  # -log10(mol/kg)
        except Exception as e:
            logger.error(f"LD50 model prediction failed: {e}")
            return None
        mol_per_kg = 10 ** (-y)
        ld50_mg_kg = mol_per_kg * mw * 1000
        category, ld50_range = self.ld50_mgkg_to_category(ld50_mg_kg)
        # Confidence reflects the model's benchmark test R2 (~0.55)
        r2 = (self.ld50_meta or {}).get('test_r2', 0.5)
        confidence = int(round(55 + 25 * max(0.0, min(1.0, r2))))
        return {
            'category': category,
            'ld50_range': ld50_range,
            'ld50_mg_kg': round(ld50_mg_kg, 1),
            'confidence': confidence,
            'source': 'ml_model',
            'source_detail': (self.ld50_meta or {}).get('source', 'trained model'),
        }

    def _parse_dose_mgkg(self, dose_str):
        """Parse a ChemIDplus dose string like '250 mg/kg' -> 250.0 (mg/kg)."""
        if not dose_str:
            return None
        m = re.match(r'([\d.]+)\s*(mg|gm|g|ug|mcg|ng)/kg', dose_str.strip(), re.I)
        if not m:
            return None
        val = float(m.group(1))
        unit = m.group(2).lower()
        factor = {'mg': 1, 'gm': 1000, 'g': 1000, 'ug': 1e-3, 'mcg': 1e-3, 'ng': 1e-6}[unit]
        return val * factor

    def get_experimental_ld50(self, drug_name, cid=None, route='oral', species='Mouse'):
        """
        Fetch REAL experimental LD50 values from PubChem's ChemIDplus records.
        Prefers the requested species (Mouse or Rat), then the other rodent,
        and matching administration route.
        Returns dict with 'found' and (if found) the best LD50 in mg/kg.
        """
        preferred = (species or 'Mouse').strip().lower()
        if preferred not in ('mouse', 'rat'):
            preferred = 'mouse'
        cache_key = {'drug': drug_name.lower(), 'route': route.lower(),
                     'species': preferred, 'type': 'exp_ld50'}
        if self.cache:
            cached = self.cache.get('experimental_ld50', cache_key)
            if cached:
                return cached

        result = {'found': False}
        try:
            if cid is None:
                cid_data = get_drug_data_from_ncbi(drug_name)
                cid = cid_data.get('cid') if cid_data.get('success') else None
            if not cid:
                return result

            # Step 1: find the ChemIDplus SID from the Acute Effects section
            try:
                resp = requests.get(
                    f"{Config.PUBCHEM_PUGVIEW_BASE}/{cid}/JSON",
                    params={'heading': 'Acute Effects'},
                    timeout=Config.REQUEST_TIMEOUT)
                resp.raise_for_status()
                record = resp.json().get('Record', {})
            except requests.exceptions.HTTPError:
                # 404 = no acute-effects data for this compound -> fall back to model
                if self.cache:
                    self.cache.set('experimental_ld50', cache_key, result)
                return result

            def find_sid(sec):
                for s in sec.get('Section', []):
                    for info in s.get('Information', []):
                        ext = info.get('Value', {}).get('ExternalTableName', '')
                        m = re.search(r'query=(\d+)', ext)
                        if m:
                            return m.group(1)
                    found = find_sid(s)
                    if found:
                        return found
                return None

            sid = find_sid(record)
            if not sid:
                if self.cache:
                    self.cache.set('experimental_ld50', cache_key, result)
                return result

            # Step 2: pull the ChemIDplus toxicity rows via the SDQ endpoint
            query = ('{"select":"*","collection":"chemidplus","where":{"ands":'
                     '[{"sid":"%s"}]},"order":["relevancescore,desc"],'
                     '"start":1,"limit":80}') % sid
            resp = requests.get(
                Config.PUBCHEM_SDQ,
                params={'infmt': 'json', 'outfmt': 'json', 'query': query},
                timeout=Config.REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            rows = data if isinstance(data, list) else \
                data.get('SDQOutputSet', [{}])[0].get('rows', [])

            ld50_entries = []
            for row in rows:
                if row.get('testtype') != 'LD50':
                    continue
                mg = self._parse_dose_mgkg(row.get('dose', ''))
                if mg is None or mg <= 0:
                    continue
                ld50_entries.append({
                    'organism': row.get('organism', ''),
                    'route': row.get('route', ''),
                    'ld50_mg_kg': round(mg, 2),
                })

            if not ld50_entries:
                if self.cache:
                    self.cache.set('experimental_ld50', cache_key, result)
                return result

            # Step 3: rank — mouse > rat, and matching route preferred.
            # Map short route codes to the terms ChemIDplus actually uses.
            route_synonyms = {
                'oral': ['oral'],
                'iv': ['intravenous'], 'intravenous': ['intravenous'],
                'ip': ['intraperitoneal'], 'intraperitoneal': ['intraperitoneal'],
                'sc': ['subcutaneous'], 'subcutaneous': ['subcutaneous'],
                'im': ['intramuscular'], 'intramuscular': ['intramuscular'],
                'icv': ['intracerebral', 'intracranial'],
            }
            wanted_routes = route_synonyms.get(route.lower(), [route.lower()])

            other_rodent = 'rat' if preferred == 'mouse' else 'mouse'

            def rank(e):
                s = 0
                org = e['organism'].lower()
                if org == preferred:
                    s += 4            # the species the user selected
                elif org == other_rodent:
                    s += 3            # the other rodent
                er = (e['route'] or '').lower()
                if er and any(w in er for w in wanted_routes):
                    s += 2
                return -s
            ld50_entries.sort(key=rank)
            best = ld50_entries[0]
            category, ld50_range = self.ld50_mgkg_to_category(best['ld50_mg_kg'])

            result = {
                'found': True,
                'category': category,
                'ld50_range': ld50_range,
                'ld50_mg_kg': best['ld50_mg_kg'],
                'confidence': 95,  # real experimental value
                'source': 'experimental',
                'source_detail': f"PubChem/ChemIDplus ({best['organism']}, {best['route']})",
                'best': best,
                'all_values': ld50_entries[:12],
            }
        except Exception as e:
            logger.error(f"Experimental LD50 lookup failed for {drug_name}: {e}")
            return {'found': False}

        if self.cache:
            self.cache.set('experimental_ld50', cache_key, result)
        return result

    def predict_ld50_hybrid(self, drug_name, smiles, descriptors, cid=None, route='oral'):
        """
        Hybrid LD50 prediction:
          1. real experimental value (PubChem/ChemIDplus) if available,
          2. otherwise the trained ML model,
          3. otherwise the molecular-property heuristic.
        Always returns the same shape used downstream.
        """
        # 1) real experimental data
        exp = self.get_experimental_ld50(drug_name, cid=cid, route=route)
        if exp.get('found'):
            return {
                'category': exp['category'],
                'ld50_range': exp['ld50_range'],
                'ld50_mg_kg': exp['ld50_mg_kg'],
                'confidence': exp['confidence'],
                'source': 'experimental',
                'source_detail': exp['source_detail'],
                'experimental_values': exp.get('all_values', []),
            }

        # 2) trained ML model
        ml = self.predict_ld50_ml(smiles)
        if ml is not None:
            return ml

        # 3) heuristic fallback
        heur = self._predict_ld50_heuristic(descriptors)
        heur['source'] = 'heuristic'
        heur['source_detail'] = 'molecular-property rules (no data/model available)'
        return heur

    def _predict_ld50_heuristic(self, descriptors):
        """
        LAST-RESORT rule-based LD50 estimate from molecular properties.
        Used only when neither experimental data nor the trained model apply.
        Categories (mg/kg): high (<50), moderate (50-500), low (500-2000), very_low (>2000)
        """
        mw = descriptors.get('molecular_weight', 300)
        logp = descriptors.get('logp', 2.0)
        h_donors = descriptors.get('h_donors', 2)
        tpsa = descriptors.get('tpsa', 75)

        score = 0
        if mw > 500:
            score += 2
        elif mw > 300:
            score += 1
        if 0 < logp < 3:
            score += 2
        elif logp < 5:
            score += 1
        if h_donors >= 3:
            score += 1
        if tpsa > 100:
            score += 2
        elif tpsa > 60:
            score += 1

        if score >= 6:
            category, ld50_range, confidence = 'very_low', (2000, 99999), 55
        elif score >= 4:
            category, ld50_range, confidence = 'low', (500, 2000), 50
        elif score >= 2:
            category, ld50_range, confidence = 'moderate', (50, 500), 45
        else:
            category, ld50_range, confidence = 'high', (1, 50), 40

        return {
            'category': category,
            'ld50_range': ld50_range,
            'confidence': confidence,
            'score': score,
        }

    # Backwards-compatible alias (older callers used predict_ld50_category)
    def predict_ld50_category(self, descriptors):
        return self._predict_ld50_heuristic(descriptors)

    def predict_organ_toxicity(self, descriptors, weight=25, age=8, route='oral', dose=10):
        """
        Predict organ-specific toxicity risks with detailed mouse-specific factors.
        
        Args:
            descriptors: Molecular descriptors
            weight: Mouse weight in grams
            age: Mouse age in weeks
            route: Administration route
            dose: Dose in mg/kg
        """
        logp = descriptors.get('logp', 2.0)
        mw = descriptors.get('molecular_weight', 300)
        aromatic = descriptors.get('aromatic_rings', 1)
        tpsa = descriptors.get('tpsa', 75)
        
        risks = {}
        
        # === LIVER TOXICITY ===
        liver_risk_score = 0
        
        # Base molecular risk
        if logp > 4:
            liver_risk_score += 3  # High lipophilicity = hepatic accumulation
        elif logp > 2:
            liver_risk_score += 1
        
        # Dose-dependent hepatotoxicity
        if dose > 100:
            liver_risk_score += 2  # High dose increases liver stress
        elif dose > 50:
            liver_risk_score += 1
        
        # Age factor: old mice more susceptible
        if age > 18:
            liver_risk_score += 1  # Aging liver less efficient
        elif age < 6:
            liver_risk_score += 1  # Immature liver enzymes
        
        # Route factor: oral = first-pass metabolism
        if route.lower() == 'oral':
            liver_risk_score += 1
        
        # Weight factor: smaller mice = higher relative exposure
        if weight < 20:
            liver_risk_score += 1
        
        # Classify liver risk
        if liver_risk_score >= 5:
            risks['liver'] = 'high'
        elif liver_risk_score >= 3:
            risks['liver'] = 'moderate'
        else:
            risks['liver'] = 'low'
        
        # === KIDNEY TOXICITY ===
        kidney_risk_score = 0
        
        # Small molecular weight = renal clearance
        if mw < 300 and logp < 1:
            kidney_risk_score += 2
        
        # High dose = renal stress
        if dose > 100:
            kidney_risk_score += 2
        elif dose > 50:
            kidney_risk_score += 1
        
        # Age: old mice have reduced renal function
        if age > 18:
            kidney_risk_score += 2
        
        # Route: IV/IP = direct systemic exposure
        if route.lower() in ['iv', 'ip']:
            kidney_risk_score += 1
        
        if kidney_risk_score >= 4:
            risks['kidney'] = 'high'
        elif kidney_risk_score >= 2:
            risks['kidney'] = 'moderate'
        else:
            risks['kidney'] = 'low'
        
        # === HEART TOXICITY ===
        heart_risk_score = 0
        
        # Aromatic rings = cardiotoxic potential
        if aromatic >= 3:
            heart_risk_score += 2
        elif aromatic >= 2:
            heart_risk_score += 1
        
        # High dose
        if dose > 100:
            heart_risk_score += 2
        
        # Age: old mice more susceptible to cardiac issues
        if age > 18:
            heart_risk_score += 2
        
        # Route: IV = rapid cardiac exposure
        if route.lower() == 'iv':
            heart_risk_score += 1
        
        if heart_risk_score >= 4:
            risks['heart'] = 'high'
        elif heart_risk_score >= 2:
            risks['heart'] = 'moderate'
        else:
            risks['heart'] = 'low'
        
        # === BRAIN/CNS TOXICITY ===
        brain_risk_score = 0
        
        # BBB penetration (LogP 2-3 optimal, >3 = excessive)
        if logp > 4:
            brain_risk_score += 2
        elif logp > 3:
            brain_risk_score += 1
        
        # Low TPSA = better BBB penetration = higher CNS exposure
        if tpsa < 60:
            brain_risk_score += 2
        elif tpsa < 90:
            brain_risk_score += 1
        
        # High dose
        if dose > 50:
            brain_risk_score += 1
        
        # Age: young and old more susceptible to neurotoxicity
        if age < 6 or age > 18:
            brain_risk_score += 1
        
        # Route: ICV = direct CNS exposure
        if route.lower() == 'icv':
            brain_risk_score += 3
        
        if brain_risk_score >= 5:
            risks['brain'] = 'high'
        elif brain_risk_score >= 3:
            risks['brain'] = 'moderate'
        else:
            risks['brain'] = 'low'
        
        # === LUNG TOXICITY ===
        lung_risk_score = 0
        
        # High molecular weight particles
        if mw > 500:
            lung_risk_score += 1
        
        # High dose
        if dose > 100:
            lung_risk_score += 1
        
        # Age: old mice
        if age > 18:
            lung_risk_score += 1
        
        if lung_risk_score >= 2:
            risks['lung'] = 'moderate'
        else:
            risks['lung'] = 'low'
        
        # === GI TRACT TOXICITY ===
        gi_risk_score = 0
        
        # Oral route = direct GI exposure
        if route.lower() == 'oral':
            gi_risk_score += 2
        
        # High dose
        if dose > 100:
            gi_risk_score += 2
        elif dose > 50:
            gi_risk_score += 1
        
        # Young mice = sensitive GI
        if age < 6:
            gi_risk_score += 1
        
        if gi_risk_score >= 3:
            risks['gi_tract'] = 'moderate'
        else:
            risks['gi_tract'] = 'low'
        
        return risks
    
    def get_safe_dose_recommendations(self, ld50_category, route='oral'):
        """Calculate safe starting doses based on LD50 category."""
        dose_guidelines = {
            'very_low': {
                'starting_dose': '10-50 mg/kg',
                'max_dose': '500 mg/kg',
                'escalation': 'Can escalate rapidly (2x per week)',
                'monitoring': 'Standard monitoring sufficient'
            },
            'low': {
                'starting_dose': '5-20 mg/kg',
                'max_dose': '100 mg/kg',
                'escalation': 'Moderate escalation (1.5x per week)',
                'monitoring': 'Weekly health checks recommended'
            },
            'moderate': {
                'starting_dose': '1-5 mg/kg',
                'max_dose': '20 mg/kg',
                'escalation': 'Slow escalation (1.2x per week)',
                'monitoring': 'Daily health checks required'
            },
            'high': {
                'starting_dose': '0.1-1 mg/kg',
                'max_dose': '5 mg/kg',
                'escalation': 'Very slow escalation (1.1x per week)',
                'monitoring': 'Continuous monitoring required + veterinary oversight'
            }
        }
        
        return dose_guidelines.get(ld50_category, dose_guidelines['moderate'])
    
    def adjust_toxicity_for_dose(self, ld50_pred, dose, weight, age, route):
        """
        Adjust toxicity prediction based on actual dose vs LD50 range.
        
        Returns adjusted toxicity category and safety margin.
        """
        ld50_range = ld50_pred['ld50_range']
        ld50_low = ld50_range[0]
        ld50_high = ld50_range[1]
        ld50_mid = (ld50_low + ld50_high) / 2
        
        # Calculate safety margin (therapeutic index)
        safety_margin = ld50_mid / dose if dose > 0 else 999
        
        # Adjust for age
        if age < 6:
            safety_margin *= 0.8  # Young mice more sensitive
        elif age > 18:
            safety_margin *= 0.7  # Old mice more sensitive
        
        # Adjust for weight
        if weight < 20:
            safety_margin *= 0.85  # Smaller mice higher exposure
        
        # Adjust for route
        route_factors = {
            'oral': 1.0,
            'ip': 0.9,
            'iv': 0.8,  # More dangerous
            'sc': 0.95,
            'im': 0.9,
            'icv': 0.6  # Most dangerous
        }
        safety_margin *= route_factors.get(route.lower(), 1.0)
        
        # Classify safety
        if safety_margin > 100:
            safety_class = 'very_safe'
            adjusted_category = 'very_low'
        elif safety_margin > 10:
            safety_class = 'safe'
            adjusted_category = 'low'
        elif safety_margin > 5:
            safety_class = 'caution'
            adjusted_category = 'moderate'
        elif safety_margin > 2:
            safety_class = 'warning'
            adjusted_category = 'moderate-high'
        else:
            safety_class = 'danger'
            adjusted_category = 'high'
        
        return {
            'adjusted_category': adjusted_category,
            'safety_margin': round(safety_margin, 2),
            'safety_class': safety_class,
            'dose_is_safe': safety_margin > 10,
            'ld50_estimate': ld50_mid,
            'percentage_of_ld50': round((dose / ld50_mid) * 100, 1) if dose > 0 else 0
        }
    
    def calculate_overall_risk_score(self, toxicity_category, organ_risks, dose, age, weight, route):
        """
        Calculate overall risk score (0-100).
        Higher score = higher risk.
        """
        score = 0
        
        # Base toxicity category
        tox_scores = {'very_low': 10, 'low': 20, 'moderate': 40, 'high': 60}
        score += tox_scores.get(toxicity_category, 40)
        
        # Organ risks
        high_risk_organs = sum(1 for risk in organ_risks.values() if risk == 'high')
        moderate_risk_organs = sum(1 for risk in organ_risks.values() if risk == 'moderate')
        score += high_risk_organs * 10
        score += moderate_risk_organs * 5
        
        # Dose
        if dose > 100:
            score += 15
        elif dose > 50:
            score += 8
        
        # Age
        if age < 6 or age > 18:
            score += 10
        
        # Weight
        if weight < 20:
            score += 5
        
        # Route
        route_risk = {'oral': 0, 'sc': 5, 'im': 5, 'ip': 10, 'iv': 15, 'icv': 20}
        score += route_risk.get(route.lower(), 0)
        
        return min(100, score)
    
    def interpret_risk_score(self, score):
        """Interpret overall risk score."""
        if score < 20:
            return 'MINIMAL RISK - Proceed with standard protocols'
        elif score < 40:
            return 'LOW RISK - Monitor animals regularly'
        elif score < 60:
            return 'MODERATE RISK - Enhanced monitoring required'
        elif score < 80:
            return 'HIGH RISK - Continuous monitoring essential, veterinary oversight'
        else:
            return 'CRITICAL RISK - Reconsider study, reduce dose, or use alternative compound'

    def generate_welfare_recommendations(self, risk_score, organ_risks=None,
                                         pct_ld50=0, target_organ=None):
        """
        Derive HUMANE ENDPOINTS (IACUC Part 8) and PAIN/DISTRESS MONITORING
        (Part 11) from the toxicity assessment. These map directly onto the
        animal-ethics protocol so a researcher can reuse them.

        DECISION-SUPPORT ONLY — must be reviewed by the researcher and the
        attending veterinarian. Does NOT cover the euthanasia METHOD (that is
        institutionally standardised and out of scope).
        """
        organ_risks = dict(organ_risks or {})
        # If only a single target organ is known (comprehensive endpoint),
        # infer its risk from the overall score.
        if not organ_risks and target_organ and target_organ.lower() not in ('general', '', 'none'):
            level = 'high' if risk_score >= 60 else 'moderate' if risk_score >= 40 else 'low'
            organ_risks = {target_organ.lower(): level}

        # --- Humane endpoints (Part 8) ---
        humane_endpoints = [
            "Body weight loss ≥ 20% from baseline (or ≥ 15% with other clinical signs)",
            "Body condition score ≤ 2/5 (emaciation)",
            "Prolonged anorexia or inability to reach food/water (>24 h)",
            "Persistent hypothermia, hunched posture, or lack of grooming",
        ]
        organ_signs = {
            'liver': "hepatotoxicity signs — jaundice, marked lethargy, abnormal bleeding",
            'kidney': "nephrotoxicity signs — reduced urination, oedema, dehydration",
            'brain': "neurological signs — seizures, tremors, paralysis, circling, ataxia",
            'heart': "cardiovascular signs — cyanosis, laboured breathing, collapse",
            'lung': "respiratory distress — dyspnoea, gasping, cyanosis",
        }
        for organ, risk in organ_risks.items():
            key = organ.lower()
            if risk in ('high', 'moderate') and key in organ_signs:
                humane_endpoints.append(
                    f"[{key.upper()} risk: {risk}] Monitor for {organ_signs[key]}")

        if pct_ld50 and pct_ld50 >= 25:
            humane_endpoints.append(
                f"Dose is ~{round(pct_ld50, 1)}% of the estimated LD50 — watch closely for "
                f"acute toxicity; euthanise on moderate–severe distress that does not resolve.")

        # --- Pain / distress monitoring (Part 11) ---
        if risk_score >= 60:
            level = 'high'
            frequency = "At least twice daily (≈12 h apart); continuous around peak drug effect."
        elif risk_score >= 40:
            level = 'moderate'
            frequency = "Once daily, with additional checks after each dosing event."
        else:
            level = 'low'
            frequency = "Every 2–3 days; daily around dosing events."

        if risk_score >= 40:
            analgesia = ("Provide analgesia/anti-inflammatory as advised by the veterinarian; "
                         "do not withhold without scientific justification (Part 11).")
        else:
            analgesia = ("Analgesia likely not required for routine handling/injection; "
                         "reassess promptly if any distress is observed.")

        return {
            'disclaimer': ("Decision-support suggestions derived from predicted toxicity. "
                           "Must be reviewed and approved by the researcher and attending "
                           "veterinarian before use in a protocol."),
            'humane_endpoints': humane_endpoints,
            'monitoring': {
                'level': level,
                'frequency': frequency,
                'analgesia_guidance': analgesia,
                'body_condition_scoring': ("Record body weight and body condition score (1–5) "
                                           "at each observation."),
            },
            'response_when_endpoint_reached': (
                "Remove the animal from study and apply the approved euthanasia method "
                "immediately; record observations and notify the veterinarian."),
        }

    def get_chembl_toxicity(self, drug_name):
        """Search ChEMBL for experimental toxicity data."""
        cache_key = {'drug': drug_name.lower()}
        if self.cache:
            cached = self.cache.get('chembl_toxicity', cache_key)
            if cached:
                return cached
        
        try:
            # Search ChEMBL for compound
            search_url = f"{Config.CHEMBL_BASE}/molecule/search.json"
            params = {'q': drug_name, 'limit': 1}
            
            response = requests.get(search_url, params=params, timeout=Config.CHEMBL_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            molecules = data.get('molecules', [])
            
            if not molecules:
                return {'success': False, 'error': 'No data in ChEMBL'}
            
            chembl_id = molecules[0]['molecule_chembl_id']
            
            # Get bioactivity data (including toxicity assays)
            activity_url = f"{Config.CHEMBL_BASE}/activity.json"
            params = {
                'molecule_chembl_id': chembl_id,
                'limit': 50,
                'assay_type': 'ADMET'  # Focus on ADMET assays
            }
            
            response = requests.get(activity_url, params=params, timeout=Config.CHEMBL_TIMEOUT)
            response.raise_for_status()
            
            activity_data = response.json()
            activities = activity_data.get('activities', [])
            
            result = {
                'success': True,
                'chembl_id': chembl_id,
                'num_assays': len(activities),
                'has_toxicity_data': len(activities) > 0
            }
            
            if self.cache:
                self.cache.set('chembl_toxicity', cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"ChEMBL toxicity search failed for {drug_name}: {e}")
            return {'success': False, 'error': str(e)}
    
    def predict_toxicity_comprehensive(self, drug_name, route='oral', target_organ=None,
                                      weight=25, age=8, dose=10):
        """
        Main toxicity prediction function with mouse-specific parameters.
        
        Args:
            drug_name: Name of the drug
            route: Administration route
            target_organ: Target organ/system
            weight: Mouse weight in grams
            age: Mouse age in weeks
            dose: Dose in mg/kg
        
        Returns comprehensive toxicity assessment.
        """
        logger.info(f"Predicting toxicity for: {drug_name} (dose={dose} mg/kg, route={route}, weight={weight}g, age={age}w)")
        
        # Step 1: Get chemical structure
        structure = self.get_chemical_structure(drug_name)
        if not structure['success']:
            return {
                'success': False,
                'error': structure['error'],
                'drug_name': drug_name
            }
        
        smiles = structure['smiles']
        
        # Step 2: Calculate molecular descriptors
        desc_result = self.calculate_molecular_descriptors(smiles)
        if not desc_result['success']:
            return {
                'success': False,
                'error': desc_result['error'],
                'drug_name': drug_name
            }
        
        descriptors = desc_result['descriptors']
        
        # Step 3: Predict LD50 (HYBRID: real experimental data -> trained ML -> heuristic)
        ld50_pred = self.predict_ld50_hybrid(
            drug_name, smiles, descriptors,
            cid=structure.get('cid'), route=route
        )
        logger.info(
            f"LD50 for {drug_name}: {ld50_pred.get('ld50_mg_kg', '?')} mg/kg "
            f"[{ld50_pred['category']}] via {ld50_pred.get('source', 'unknown')}"
        )

        # Adjust toxicity based on actual dose
        dose_adjusted_toxicity = self.adjust_toxicity_for_dose(
            ld50_pred, dose, weight, age, route
        )
        
        # Step 4: Predict organ toxicity with mouse-specific factors
        organ_risks = self.predict_organ_toxicity(
            descriptors, weight=weight, age=age, route=route, dose=dose
        )
        
        # Step 5: Get safe dose recommendations
        dose_recs = self.get_safe_dose_recommendations(ld50_pred['category'], route)
        
        # Step 6: Get experimental data from ChEMBL
        chembl_data = self.get_chembl_toxicity(drug_name)
        
        # Step 7: Generate warnings (dose and age-specific)
        warnings = []
        if ld50_pred['category'] in ['high', 'moderate']:
            warnings.append(f"⚠️ {ld50_pred['category'].upper()} toxicity predicted - use caution")
        
        # Dose-specific warnings
        if dose > 100:
            warnings.append(f"⚠️ HIGH DOSE ({dose} mg/kg) - Increased toxicity risk across all organs")
        elif dose > 50:
            warnings.append(f"⚠️ Moderate dose ({dose} mg/kg) - Monitor for adverse effects")
        
        # Age-specific warnings
        if age < 6:
            warnings.append(f"⚠️ Young mice (age {age}w) - Immature organ systems, use lower doses")
        elif age > 18:
            warnings.append(f"⚠️ Aged mice (age {age}w) - Reduced organ function, monitor closely")
        
        # Weight-specific warnings
        if weight < 20:
            warnings.append(f"⚠️ Low body weight ({weight}g) - Higher relative drug exposure")
        
        # Route-specific warnings
        if route.lower() == 'iv':
            warnings.append(f"⚠️ IV route - Rapid systemic exposure, monitor for acute toxicity")
        elif route.lower() == 'icv':
            warnings.append(f"⚠️ ICV route - Direct CNS exposure, high neurotoxicity risk")
        
        # Organ-specific warnings
        for organ, risk in organ_risks.items():
            if risk == 'high':
                warnings.append(f"⚠️ HIGH {organ.upper()} toxicity risk - close monitoring essential")
            elif risk == 'moderate' and organ == target_organ.lower() if target_organ else False:
                warnings.append(f"⚠️ MODERATE {organ.upper()} toxicity risk in target organ")
        
        # Calculate overall risk score (0-100)
        risk_score = self.calculate_overall_risk_score(
            ld50_pred['category'], organ_risks, dose, age, weight, route
        )

        # Derive IACUC welfare recommendations (humane endpoints + pain monitoring)
        welfare = self.generate_welfare_recommendations(
            risk_score, organ_risks=organ_risks,
            pct_ld50=dose_adjusted_toxicity.get('percentage_of_ld50', 0),
            target_organ=target_organ
        )

        # Final result
        return {
            'success': True,
            'drug_name': drug_name,
            'toxicity_category': ld50_pred['category'],
            'ld50_range': ld50_pred['ld50_range'],
            'ld50_mg_kg': ld50_pred.get('ld50_mg_kg'),
            'ld50_source': ld50_pred.get('source', 'unknown'),
            'ld50_source_detail': ld50_pred.get('source_detail', ''),
            'experimental_ld50_values': ld50_pred.get('experimental_values', []),
            'confidence': ld50_pred['confidence'],
            'organ_toxicity': organ_risks,
            'dose_recommendations': dose_recs,
            'molecular_properties': descriptors,
            'chembl_data': chembl_data,
            'warnings': warnings,
            'route': route,
            'target_organ': target_organ,
            'mouse_parameters': {
                'weight_g': weight,
                'age_weeks': age,
                'dose_mg_kg': dose
            },
            'dose_adjusted_toxicity': dose_adjusted_toxicity,
            'overall_risk_score': risk_score,
            'risk_interpretation': self.interpret_risk_score(risk_score),
            'welfare_recommendations': welfare
        }


# ============================================================================
# EFFECTIVENESS PREDICTION
# ============================================================================

class EffectivenessPredictor:
    """
    Predict drug effectiveness using bioactivity data and literature.
    Integrates with existing search functions.
    """
    
    def __init__(self):
        self.cache = None  # Will be set after api_cache is initialized
        logger.info("EffectivenessPredictor initialized")
    
    def search_target_activity(self, drug_name, target_organ=None):
        """Search ChEMBL for target activity data."""
        cache_key = {'drug': drug_name.lower(), 'target': target_organ or 'general'}
        if self.cache:
            cached = self.cache.get('chembl_activity', cache_key)
            if cached:
                return cached
        
        try:
            # Search ChEMBL for compound
            search_url = f"{Config.CHEMBL_BASE}/molecule/search.json"
            response = requests.get(search_url, params={'q': drug_name, 'limit': 1},
                                  timeout=Config.CHEMBL_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            molecules = data.get('molecules', [])
            
            if not molecules:
                return {'success': False, 'error': 'No data found'}
            
            chembl_id = molecules[0]['molecule_chembl_id']
            
            # Get bioactivity data
            activity_url = f"{Config.CHEMBL_BASE}/activity.json"
            params = {
                'molecule_chembl_id': chembl_id,
                'limit': 100
            }
            
            response = requests.get(activity_url, params=params, timeout=Config.CHEMBL_TIMEOUT)
            response.raise_for_status()
            
            activity_data = response.json()
            activities = activity_data.get('activities', [])
            
            # Extract IC50/EC50 values
            potency_values = []
            for activity in activities:
                if activity.get('standard_type') in ['IC50', 'EC50', 'Ki']:
                    value = activity.get('standard_value')
                    if value:
                        try:
                            potency_values.append(float(value))
                        except:
                            pass
            
            result = {
                'success': True,
                'chembl_id': chembl_id,
                'num_activities': len(activities),
                'potency_values': potency_values,
                'median_potency': np.median(potency_values) if potency_values else None
            }
            
            if self.cache:
                self.cache.set('chembl_activity', cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"ChEMBL activity search failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def predict_efficacy_from_potency(self, potency_values):
        """Predict efficacy category from IC50/EC50 values."""
        if not potency_values:
            return {
                'category': 'unknown',
                'confidence': 0,
                'note': 'No potency data available'
            }
        
        median_potency = np.median(potency_values)  # nM units
        
        # Classify based on median potency
        if median_potency < 10:
            category = 'very_high'
            confidence = 85
        elif median_potency < 100:
            category = 'high'
            confidence = 75
        elif median_potency < 1000:
            category = 'moderate'
            confidence = 65
        elif median_potency < 10000:
            category = 'low'
            confidence = 55
        else:
            category = 'very_low'
            confidence = 50
        
        return {
            'category': category,
            'median_potency_nM': median_potency,
            'confidence': confidence,
            'num_datapoints': len(potency_values)
        }
    
    def search_clinical_efficacy(self, drug_name, condition=None):
        """Mine PubMed for efficacy reports using existing function."""
        # Use existing PubMed search
        group = {'drug_name': drug_name, 'target_organ': condition or ''}
        papers = search_pubmed_articles(group, max_results=20)
        
        # Count positive/negative outcomes in abstracts/titles
        positive_keywords = ['effective', 'improved', 'beneficial', 'significant improvement']
        negative_keywords = ['ineffective', 'no effect', 'failed', 'not significant']
        
        positive_count = 0
        negative_count = 0
        
        for paper in papers:
            title = paper.get('title', '').lower()
            
            if any(kw in title for kw in positive_keywords):
                positive_count += 1
            if any(kw in title for kw in negative_keywords):
                negative_count += 1
        
        total = positive_count + negative_count
        success_rate = (positive_count / total * 100) if total > 0 else 50
        
        return {
            'total_papers': len(papers),
            'positive_outcomes': positive_count,
            'negative_outcomes': negative_count,
            'success_rate_percent': round(success_rate, 1),
            'papers': papers[:5]  # Top 5 papers
        }
    
    def predict_optimal_dose(self, efficacy_data, toxicity_category=None):
        """Estimate optimal therapeutic dose range."""
        median_potency = efficacy_data.get('median_potency_nM')
        
        if not median_potency:
            return {
                'starting_dose': '1-10 mg/kg',
                'max_dose': '50 mg/kg',
                'note': 'Based on typical ranges - no potency data'
            }
        
        # Convert in vitro potency to in vivo estimate (rough multiplier)
        # Typical multiplier: 100-1000x for in vivo vs in vitro
        in_vivo_estimate_low = (median_potency / 1000) * 0.1  # mg/kg
        in_vivo_estimate_high = (median_potency / 1000) * 1.0  # mg/kg
        
        # Adjust based on toxicity if provided
        if toxicity_category in ['high', 'moderate']:
            in_vivo_estimate_low *= 0.5
            in_vivo_estimate_high *= 0.5
        
        return {
            'starting_dose': f"{max(0.1, in_vivo_estimate_low):.1f}-{in_vivo_estimate_high:.1f} mg/kg",
            'max_dose': f"{in_vivo_estimate_high * 5:.1f} mg/kg",
            'based_on': f'In vitro potency {median_potency:.0f} nM'
        }
    
    def adjust_efficacy_for_mouse_parameters(self, efficacy_pred, dose, weight, age, route, target_organ):
        """
        Adjust efficacy prediction based on mouse-specific parameters.
        Returns adjusted efficacy score (0-100) and category.
        """
        # Base efficacy score from prediction
        base_scores = {
            'very_high': 90,
            'high': 75,
            'moderate': 50,
            'low': 30,
            'very_low': 15,
            'unknown': 40
        }
        efficacy_score = base_scores.get(efficacy_pred.get('category', 'unknown'), 40)
        
        # === Dose adjustments ===
        # Assume optimal dose is around 10 mg/kg (adjust based on your needs)
        optimal_dose_low = 5
        optimal_dose_high = 50
        
        if dose < optimal_dose_low:
            # Sub-therapeutic dose
            dose_factor = (dose / optimal_dose_low)  # 0-1
            efficacy_score *= dose_factor
        elif dose > optimal_dose_high:
            # Supra-therapeutic dose (diminishing returns)
            excess_ratio = (dose - optimal_dose_high) / optimal_dose_high
            efficacy_score *= (1 - min(0.3, excess_ratio * 0.1))
        
        # === Age adjustments ===
        if age < 6:
            # Young mice - immature target systems
            efficacy_score *= 0.85
        elif age > 18:
            # Old mice - altered pharmacodynamics
            efficacy_score *= 0.9
        
        # === Weight adjustments ===
        if weight < 20:
            # Smaller mice may have different volume of distribution
            efficacy_score *= 0.95
        elif weight > 35:
            # Larger mice
            efficacy_score *= 0.97
        
        # === Route adjustments (bioavailability) ===
        route_bioavailability = {
            'iv': 1.0,      # 100% bioavailability
            'ip': 0.95,     # ~95%
            'sc': 0.9,      # ~90%
            'im': 0.9,      # ~90%
            'oral': 0.6,    # ~60% (first-pass metabolism)
            'icv': 1.0      # Direct CNS
        }
        bioavail = route_bioavailability.get(route.lower(), 0.7)
        efficacy_score *= bioavail
        
        # === Target organ accessibility ===
        if target_organ:
            target_lower = target_organ.lower()
            
            # Brain/CNS - BBB barrier
            if 'brain' in target_lower or 'cns' in target_lower or 'neuro' in target_lower:
                if route.lower() == 'icv':
                    efficacy_score *= 1.2  # Direct CNS access
                elif route.lower() == 'oral':
                    efficacy_score *= 0.7  # BBB limitation
            
            # Liver - high first-pass for oral
            elif 'liver' in target_lower or 'hepatic' in target_lower:
                if route.lower() == 'oral':
                    efficacy_score *= 1.1  # Good liver exposure
            
            # Kidney
            elif 'kidney' in target_lower or 'renal' in target_lower:
                efficacy_score *= 0.95  # Renal clearance may reduce efficacy
            
            # Tumor
            elif 'tumor' in target_lower or 'cancer' in target_lower:
                efficacy_score *= 0.8  # Tumor penetration challenge
        
        # Ensure bounds
        efficacy_score = max(0, min(100, efficacy_score))
        
        # Classify adjusted efficacy
        if efficacy_score >= 80:
            efficacy_category = 'excellent'
        elif efficacy_score >= 65:
            efficacy_category = 'good'
        elif efficacy_score >= 45:
            efficacy_category = 'moderate'
        elif efficacy_score >= 25:
            efficacy_category = 'low'
        else:
            efficacy_category = 'very_low'
        
        # Calculate success probability
        success_probability = min(95, efficacy_score)
        
        return {
            'efficacy_score': round(efficacy_score, 1),
            'efficacy_category': efficacy_category,
            'success_probability': round(success_probability, 1),
            'optimal_dose_low': optimal_dose_low,
            'optimal_dose_high': optimal_dose_high,
            'bioavailability_factor': bioavail,
            'adjustments_applied': {
                'dose': dose < optimal_dose_low or dose > optimal_dose_high,
                'age': age < 6 or age > 18,
                'weight': weight < 20 or weight > 35,
                'route': bioavail < 1.0,
                'target_accessibility': bool(target_organ)
            }
        }
    
    def calculate_expected_response_time(self, route, target_organ, dose):
        """
        Estimate expected time to effect based on route and target.
        """
        # Base response times (in days)
        route_times = {
            'iv': (1, 3, 7),        # (onset, peak, duration)
            'ip': (2, 5, 10),
            'sc': (3, 7, 14),
            'im': (3, 7, 14),
            'oral': (5, 10, 21),
            'icv': (1, 2, 5)
        }
        
        onset, peak, duration = route_times.get(route.lower(), (5, 10, 21))
        
        # Adjust for target organ
        if target_organ:
            target_lower = target_organ.lower()
            
            # CNS effects may take longer
            if 'brain' in target_lower or 'neuro' in target_lower:
                onset *= 1.5
                peak *= 1.5
                duration *= 1.2
            
            # Metabolic changes slow
            elif 'metabolic' in target_lower or 'diabetes' in target_lower:
                onset *= 2
                peak *= 2
                duration *= 1.5
            
            # Acute inflammation faster
            elif 'inflammation' in target_lower or 'pain' in target_lower:
                onset *= 0.7
                peak *= 0.8
        
        # Convert to readable format
        def days_to_str(days):
            if days < 7:
                return f"{int(days)} days"
            else:
                return f"{int(days/7)} weeks"
        
        return {
            'time_to_effect': days_to_str(onset),
            'peak_effect': days_to_str(peak),
            'duration': days_to_str(duration)
        }
    
    def estimate_pk_factors(self, route, weight, age):
        """
        Estimate pharmacokinetic factors affecting efficacy.
        """
        # Volume of distribution (mL) - roughly correlates with body weight
        vd = weight * 2.5  # Typical Vd ~ 2.5 mL/g for water-soluble drugs
        
        # Clearance adjustments
        clearance_factor = 1.0
        
        if age < 6:
            clearance_factor = 0.7  # Immature metabolism
        elif age > 18:
            clearance_factor = 0.6  # Reduced metabolism
        
        if weight < 20:
            clearance_factor *= 0.9
        
        # Half-life estimate (hours) - route dependent
        route_halflife = {
            'iv': 2,
            'ip': 3,
            'sc': 4,
            'im': 4,
            'oral': 3,
            'icv': 6
        }
        half_life = route_halflife.get(route.lower(), 3)
        half_life /= clearance_factor  # Adjust for age/weight
        
        # Dosing frequency recommendation
        if half_life < 4:
            dosing_frequency = 'Twice daily'
        elif half_life < 12:
            dosing_frequency = 'Once daily'
        else:
            dosing_frequency = 'Every 2-3 days'
        
        return {
            'volume_of_distribution_mL': round(vd, 1),
            'estimated_half_life_hours': round(half_life, 1),
            'clearance_factor': clearance_factor,
            'recommended_dosing': dosing_frequency,
            'steady_state_days': round((half_life * 5) / 24, 1)  # 5 half-lives to steady state
        }
    
    def predict_effectiveness_comprehensive(self, drug_name, condition=None, target_organ=None,
                                           weight=25, age=8, dose=10, route='oral'):
        """
        Main effectiveness prediction function with mouse-specific parameters.
        
        Args:
            drug_name: Name of the drug
            condition: Medical condition being treated
            target_organ: Target organ/system
            weight: Mouse weight in grams
            age: Mouse age in weeks
            dose: Dose in mg/kg
            route: Administration route
        
        Returns comprehensive efficacy assessment.
        """
        logger.info(f"Predicting effectiveness for: {drug_name} (dose={dose} mg/kg, route={route}, target={target_organ})")
        
        # Step 1: Search target activity
        activity = self.search_target_activity(drug_name, target_organ)
        
        # Step 2: Predict efficacy from potency
        if activity['success'] and activity.get('potency_values'):
            efficacy_pred = self.predict_efficacy_from_potency(activity['potency_values'])
        else:
            efficacy_pred = {
                'category': 'unknown',
                'confidence': 0,
                'median_potency_nM': None
            }
        
        # Step 3: Adjust efficacy based on mouse parameters
        adjusted_efficacy = self.adjust_efficacy_for_mouse_parameters(
            efficacy_pred, dose, weight, age, route, target_organ
        )
        
        # Step 4: Search clinical efficacy in literature
        lit_efficacy = self.search_clinical_efficacy(drug_name, condition)
        
        # Step 5: Combine confidence scores
        combined_confidence = (efficacy_pred.get('confidence', 0) +
                             (lit_efficacy['success_rate_percent'] if lit_efficacy['total_papers'] > 0 else 0)) / 2
        
        # Step 6: Predict optimal dose
        dose_pred = self.predict_optimal_dose(efficacy_pred)
        
        # Step 7: Calculate expected response time based on route and organ
        expected_response = self.calculate_expected_response_time(route, target_organ, dose)
        
        # Step 8: Bioavailability and pharmacokinetic considerations
        pk_factors = self.estimate_pk_factors(route, weight, age)
        
        # Step 9: Generate recommendations
        recommendations = []
        
        if adjusted_efficacy['efficacy_score'] > 80:
            recommendations.append("✓ EXCELLENT efficacy predicted - strong candidate for testing")
        elif adjusted_efficacy['efficacy_score'] > 60:
            recommendations.append("✓ GOOD efficacy predicted - recommended for testing")
        elif adjusted_efficacy['efficacy_score'] > 40:
            recommendations.append("⚠ MODERATE efficacy - consider dose optimization")
        else:
            recommendations.append("⚠ LOW efficacy predicted - may not justify animal testing")
        
        # Dose-specific recommendations
        if dose < adjusted_efficacy.get('optimal_dose_low', 0):
            recommendations.append(f"⚠ Current dose ({dose} mg/kg) may be sub-therapeutic - consider increasing")
        elif dose > adjusted_efficacy.get('optimal_dose_high', 999):
            recommendations.append(f"⚠ Current dose ({dose} mg/kg) may exceed optimal range - risk of toxicity without added benefit")
        
        # Age-specific recommendations
        if age < 6:
            recommendations.append("⚠ Young mice - efficacy may vary due to immature target systems")
        elif age > 18:
            recommendations.append("⚠ Aged mice - reduced drug metabolism may enhance efficacy but increase toxicity")
        
        # Route-specific recommendations
        if route.lower() == 'oral' and target_organ and 'brain' in target_organ.lower():
            recommendations.append("⚠ Oral route for CNS target - verify BBB permeability")
        elif route.lower() == 'iv':
            recommendations.append("✓ IV route - ensures maximum bioavailability")
        
        return {
            'success': True,
            'drug_name': drug_name,
            'efficacy_prediction': efficacy_pred['category'],
            'adjusted_efficacy': adjusted_efficacy,
            'confidence': round(combined_confidence, 1),
            'median_potency_nM': efficacy_pred.get('median_potency_nM'),
            'chembl_data': activity,
            'literature_data': lit_efficacy,
            'dose_recommendations': dose_pred,
            'expected_outcomes': {
                'time_to_effect': expected_response['time_to_effect'],
                'peak_effect': expected_response['peak_effect'],
                'duration_of_action': expected_response['duration'],
                'effect_magnitude': adjusted_efficacy['efficacy_category']
            },
            'pk_factors': pk_factors,
            'recommendations': recommendations,
            'condition': condition,
            'target_organ': target_organ,
            'mouse_parameters': {
                'weight_g': weight,
                'age_weeks': age,
                'dose_mg_kg': dose,
                'route': route
            },
            'efficacy_score': adjusted_efficacy['efficacy_score'],
            'likelihood_of_success': adjusted_efficacy['success_probability']
        }


# ============================================================================
# DECISION SUPPORT SYSTEM
# ============================================================================

def generate_overall_assessment(toxicity_result, effectiveness_result):
    """Generate overall drug assessment combining toxicity and efficacy."""
    
    # Score toxicity (lower is better)
    tox_category = toxicity_result.get('toxicity_category', 'moderate')
    tox_scores = {'very_low': 5, 'low': 4, 'moderate': 3, 'high': 2}
    tox_score = tox_scores.get(tox_category, 3)
    
    # Score efficacy (higher is better)
    eff_category = effectiveness_result.get('efficacy_prediction', 'moderate')
    eff_scores = {'very_high': 5, 'high': 4, 'moderate': 3, 'low': 2, 'very_low': 1, 'unknown': 2}
    eff_score = eff_scores.get(eff_category, 3)
    
    # Combined score (0-10)
    combined_score = tox_score + eff_score
    
    # Rating system
    if combined_score >= 9:
        rating = "⭐⭐⭐⭐⭐ EXCELLENT CANDIDATE"
        recommendation = "Highly recommended for further investigation"
    elif combined_score >= 7:
        rating = "⭐⭐⭐⭐ GOOD CANDIDATE"
        recommendation = "Recommended for testing with standard precautions"
    elif combined_score >= 5:
        rating = "⭐⭐⭐ MODERATE CANDIDATE"
        recommendation = "Proceed with caution - monitor closely"
    elif combined_score >= 3:
        rating = "⭐⭐ POOR CANDIDATE"
        recommendation = "Not recommended - high risk/low benefit"
    else:
        rating = "⭐ UNSUITABLE"
        recommendation = "Do not proceed with animal testing"
    
    # Risk-benefit ratio
    risk_benefit = calculate_risk_benefit(tox_category, eff_category)
    
    return {
        'rating': rating,
        'recommendation': recommendation,
        'combined_score': combined_score,
        'toxicity_score': tox_score,
        'efficacy_score': eff_score,
        'risk_benefit_ratio': risk_benefit
    }


def calculate_risk_benefit(toxicity_category, efficacy_category):
    """Calculate risk-benefit ratio."""
    
    # Benefit score
    benefit_map = {'very_high': 5, 'high': 4, 'moderate': 3, 'low': 2, 'very_low': 1, 'unknown': 2}
    benefit = benefit_map.get(efficacy_category, 2)
    
    # Risk score
    risk_map = {'very_low': 1, 'low': 2, 'moderate': 3, 'high': 4}
    risk = risk_map.get(toxicity_category, 3)
    
    ratio = benefit / risk if risk > 0 else 0
    
    if ratio > 2:
        assessment = "Favorable - Benefits strongly outweigh risks"
    elif ratio > 1:
        assessment = "Acceptable - Benefits outweigh risks"
    elif ratio > 0.5:
        assessment = "Marginal - Benefits and risks are balanced"
    else:
        assessment = "Unfavorable - Risks outweigh benefits"
    
    return {
        'ratio': round(ratio, 2),
        'assessment': assessment,
        'benefit_score': benefit,
        'risk_score': risk
    }


def calculate_therapeutic_window(tox_result, eff_result, current_dose):
    """
    Calculate therapeutic window and safety margin.
    
    Args:
        tox_result: Toxicity prediction result
        eff_result: Effectiveness prediction result
        current_dose: Current dose in mg/kg
    
    Returns:
        Therapeutic window analysis
    """
    # Get dose-adjusted toxicity data
    dose_adj_tox = tox_result.get('dose_adjusted_toxicity', {})
    safety_margin = dose_adj_tox.get('safety_margin', 10)
    
    # Get efficacy data
    efficacy_score = eff_result.get('efficacy_score', 50)
    adjusted_efficacy = eff_result.get('adjusted_efficacy', {})
    
    # Calculate therapeutic index (TI = TD50/ED50)
    # Approximate ED50 from efficacy data
    if efficacy_score > 60:
        estimated_ed50 = current_dose * 0.8  # Close to effective dose
    else:
        estimated_ed50 = current_dose * 1.5  # May need higher dose
    
    # TD50 from LD50 estimate (typically TD50 ~ 0.1 * LD50)
    ld50_estimate = dose_adj_tox.get('ld50_estimate', current_dose * 10)
    estimated_td50 = ld50_estimate * 0.1
    
    therapeutic_index = estimated_td50 / estimated_ed50 if estimated_ed50 > 0 else 1
    
    # Classify therapeutic window
    if therapeutic_index > 10:
        window_class = 'wide'
        window_assessment = 'WIDE therapeutic window - Safe for clinical use'
    elif therapeutic_index > 5:
        window_class = 'moderate'
        window_assessment = 'MODERATE therapeutic window - Careful dosing required'
    elif therapeutic_index > 2:
        window_class = 'narrow'
        window_assessment = 'NARROW therapeutic window - Dose monitoring essential'
    else:
        window_class = 'very_narrow'
        window_assessment = 'VERY NARROW therapeutic window - High risk, consider alternatives'
    
    # Dose recommendations
    if efficacy_score < 40:
        dose_recommendation = f"Consider increasing dose to {current_dose * 1.5:.1f} mg/kg to improve efficacy"
    elif safety_margin < 5:
        dose_recommendation = f"Consider reducing dose to {current_dose * 0.7:.1f} mg/kg to improve safety"
    else:
        dose_recommendation = f"Current dose ({current_dose} mg/kg) appears optimal"
    
    return {
        'therapeutic_index': round(therapeutic_index, 2),
        'window_class': window_class,
        'window_assessment': window_assessment,
        'estimated_ed50': round(estimated_ed50, 2),
        'estimated_td50': round(estimated_td50, 2),
        'current_dose': current_dose,
        'safety_margin': safety_margin,
        'efficacy_at_current_dose': efficacy_score,
        'dose_recommendation': dose_recommendation,
        'optimal_dose_range': {
            'min': round(estimated_ed50 * 0.8, 2),
            'max': round(estimated_td50 * 0.5, 2),  # Stay well below toxic dose
            'recommended': round((estimated_ed50 * 1.2 + estimated_td50 * 0.3) / 2, 2)
        }
    }


def assess_study_feasibility(toxicity_result, effectiveness_result):
    """Assess whether animal study should proceed."""
    
    tox_cat = toxicity_result.get('toxicity_category', 'moderate')
    eff_cat = effectiveness_result.get('efficacy_prediction', 'moderate')
    
    concerns = []
    modifications = []
    recommended = True
    
    # Check toxicity concerns
    if tox_cat == 'high':
        concerns.append("High toxicity predicted")
        modifications.append("Use lower starting dose (10% of predicted safe dose)")
        modifications.append("Implement daily health monitoring")
        modifications.append("Have veterinary support on standby")
    elif tox_cat == 'moderate':
        modifications.append("Weekly health monitoring recommended")
    
    # Check efficacy concerns
    if eff_cat in ['very_low', 'low']:
        concerns.append("Low efficacy predicted")
        modifications.append("Consider alternative compounds with better predicted efficacy")
        if eff_cat == 'very_low':
            recommended = False
            concerns.append("CRITICAL: Very low efficacy - animal study not justified")
    
    # Combined assessment
    if tox_cat == 'high' and eff_cat in ['low', 'very_low']:
        recommended = False
        concerns.append("CRITICAL: High risk + Low benefit = Study not recommended")
    
    # Calculate animals potentially saved
    if not recommended:
        animals_saved = 50  # Typical study size
    else:
        # Even if proceeding, optimized design saves animals
        if tox_cat in ['very_low', 'low'] and eff_cat in ['very_high', 'high']:
            animals_saved = 10  # Can use smaller N with strong signal
        else:
            animals_saved = 20  # Moderate savings from optimization
    
    return {
        'recommended': recommended,
        'concerns': concerns,
        'modifications': modifications,
        'animals_saved': animals_saved,
        'confidence': (toxicity_result.get('confidence', 0) + effectiveness_result.get('confidence', 0)) / 2
    }


# ============================================================================
# CACHING SYSTEM
# ============================================================================

class APICache:
    """Simple file-based cache for API responses."""
    
    def __init__(self, cache_dir=Config.CACHE_DIR, ttl_hours=Config.CACHE_EXPIRY_HOURS):
        self.cache_dir = cache_dir
        self.ttl = timedelta(hours=ttl_hours)
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_key(self, prefix, params):
        """Generate cache key from parameters."""
        key_string = f"{prefix}_{str(sorted(params.items()))}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, prefix, params):
        """Get cached data if valid."""
        try:
            cache_key = self._get_cache_key(prefix, params)
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
            
            if os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    cached = pickle.load(f)
                    if datetime.now() - cached['timestamp'] < self.ttl:
                        logger.debug(f"Cache hit for {prefix}")
                        return cached['data']
                    else:
                        os.remove(cache_file)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
        return None
    
    def set(self, prefix, params, data):
        """Store data in cache."""
        try:
            cache_key = self._get_cache_key(prefix, params)
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")
            
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'timestamp': datetime.now(),
                    'data': data
                }, f)
            logger.debug(f"Cached data for {prefix}")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

api_cache = APICache()

# Initialize prediction engines
toxicity_predictor = ToxicityPredictor()
toxicity_predictor.cache = api_cache  # Connect to cache system

effectiveness_predictor = EffectivenessPredictor()
effectiveness_predictor.cache = api_cache  # Connect to cache system

# ============================================================================
# RATE LIMITING FOR EXTERNAL APIs
# ============================================================================

class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, calls_per_second=3):
        self.calls_per_second = calls_per_second
        self.last_call = 0
    
    def wait(self):
        """Wait if necessary to respect rate limit."""
        elapsed = time.time() - self.last_call
        wait_time = (1.0 / self.calls_per_second) - elapsed
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_call = time.time()

ncbi_rate_limiter = RateLimiter(calls_per_second=3)
semantic_rate_limiter = RateLimiter(calls_per_second=2)
openalex_rate_limiter = RateLimiter(calls_per_second=2)

# ============================================================================
# MACHINE LEARNING MODEL
# ============================================================================

class SampleSizeMLModel:
    """Machine learning model for sample size prediction."""
    
    def __init__(self, model_path=Config.ML_MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self.scaler = None
        self.feature_names = [
            'dose', 'weight', 'age', 'num_groups',
            'variability_low', 'variability_medium', 'variability_high',
            'route_oral', 'route_ip', 'route_iv', 'route_sc',
            'target_brain', 'target_liver', 'target_heart', 'target_kidney',
            'strain_c57', 'strain_balb', 'sex_male', 'sex_female'
        ]
        self.load_or_create_model()
    
    def load_or_create_model(self):
        """Load existing model or create new one."""
        model_file = os.path.join(self.model_path, 'sample_size_model.pkl')
        scaler_file = os.path.join(self.model_path, 'scaler.pkl')
        
        if os.path.exists(model_file) and os.path.exists(scaler_file):
            try:
                self.model = joblib.load(model_file)
                self.scaler = joblib.load(scaler_file)
                logger.info("ML model loaded successfully")
                return
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
        
        # Create and train new model with synthetic data
        self.train_initial_model()
    
    def train_initial_model(self):
        """Train initial model with synthetic data."""
        logger.info("Training initial ML model with synthetic data...")
        
        # Generate synthetic training data based on experimental design principles
        np.random.seed(42)
        n_samples = 500
        
        # Features
        X = {
            'dose': np.random.uniform(0, 100, n_samples),
            'weight': np.random.uniform(18, 35, n_samples),
            'age': np.random.uniform(6, 20, n_samples),
            'num_groups': np.random.randint(2, 6, n_samples),
            'variability_low': np.random.binomial(1, 0.3, n_samples),
            'variability_medium': np.random.binomial(1, 0.5, n_samples),
            'variability_high': np.random.binomial(1, 0.2, n_samples),
            'route_oral': np.random.binomial(1, 0.4, n_samples),
            'route_ip': np.random.binomial(1, 0.3, n_samples),
            'route_iv': np.random.binomial(1, 0.15, n_samples),
            'route_sc': np.random.binomial(1, 0.15, n_samples),
            'target_brain': np.random.binomial(1, 0.3, n_samples),
            'target_liver': np.random.binomial(1, 0.2, n_samples),
            'target_heart': np.random.binomial(1, 0.2, n_samples),
            'target_kidney': np.random.binomial(1, 0.15, n_samples),
            'strain_c57': np.random.binomial(1, 0.7, n_samples),
            'strain_balb': np.random.binomial(1, 0.2, n_samples),
            'sex_male': np.random.binomial(1, 0.6, n_samples),
            'sex_female': np.random.binomial(1, 0.3, n_samples)
        }
        
        X_df = pd.DataFrame(X)
        
        # Target: sample size based on realistic rules
        base_n = 8
        y = np.full(n_samples, base_n)
        
        # Adjust based on features
        y += X_df['variability_high'] * 4
        y += X_df['variability_medium'] * 2
        y += X_df['target_brain'] * 2
        y += X_df['route_iv'] * 1
        y += X_df['num_groups'] * 0.5
        y += (X_df['age'] < 8) * 1
        y += (X_df['age'] > 16) * 1
        y += np.random.normal(0, 1, n_samples)  # Add noise
        y = np.clip(y, 6, 18).astype(int)
        
        # Train model
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X_df)
        
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=4,
            random_state=42
        )
        
        self.model.fit(X_scaled, y)
        
        # Save model
        joblib.dump(self.model, os.path.join(self.model_path, 'sample_size_model.pkl'))
        joblib.dump(self.scaler, os.path.join(self.model_path, 'scaler.pkl'))
        
        logger.info("ML model trained and saved")
    
    def extract_features(self, group_data):
        """Extract features from group data."""
        features = {}
        
        # Numeric features
        features['dose'] = float(group_data.get('dose', 0))
        features['weight'] = float(group_data.get('weight', 25))
        features['age'] = float(group_data.get('age', 8))
        features['num_groups'] = 2  # Will be updated based on total groups
        
        # Variability (default to medium if not specified)
        var = group_data.get('variability', 'medium').lower()
        features['variability_low'] = 1 if var == 'low' else 0
        features['variability_medium'] = 1 if var == 'medium' else 0
        features['variability_high'] = 1 if var in ['high', 'medium-high'] else 0
        
        # Route
        route = (group_data.get('route', 'oral') or 'oral').lower()
        features['route_oral'] = 1 if 'oral' in route else 0
        features['route_ip'] = 1 if 'ip' in route else 0
        features['route_iv'] = 1 if 'iv' in route else 0
        features['route_sc'] = 1 if 'sc' in route else 0
        
        # Target organ
        target = (group_data.get('target_organ', '') or '').lower()
        features['target_brain'] = 1 if 'brain' in target or 'neuro' in target else 0
        features['target_liver'] = 1 if 'liver' in target or 'hepatic' in target else 0
        features['target_heart'] = 1 if 'heart' in target or 'cardio' in target else 0
        features['target_kidney'] = 1 if 'kidney' in target or 'renal' in target else 0
        
        # Strain
        strain = (group_data.get('strain', '') or '').lower()
        features['strain_c57'] = 1 if 'c57' in strain else 0
        features['strain_balb'] = 1 if 'balb' in strain else 0
        
        # Sex
        sex = (group_data.get('sex', '') or '').lower()
        features['sex_male'] = 1 if 'male' in sex and 'female' not in sex else 0
        features['sex_female'] = 1 if 'female' in sex and 'male' not in sex else 0
        
        return pd.DataFrame([features])[self.feature_names]
    
    def predict_sample_size(self, group_data):
        """Predict optimal sample size."""
        if self.model is None:
            return None
        
        try:
            features = self.extract_features(group_data)
            features_scaled = self.scaler.transform(features)
            prediction = self.model.predict(features_scaled)[0]
            return max(6, min(18, int(round(prediction))))
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            return None

# Initialize ML model
ml_model = SampleSizeMLModel() if ML_AVAILABLE else None

# ============================================================================
# ENHANCED API FUNCTIONS - MULTIPLE SOURCES
# ============================================================================

def search_semantic_scholar(group, max_results=5):
    """Search Semantic Scholar API for papers."""
    cache_key = {
        'drug': group.get('drug_name', ''),
        'strain': group.get('strain', ''),
        'target': group.get('target_organ', ''),
        'max': max_results
    }
    
    cached = api_cache.get('semantic_scholar', cache_key)
    if cached:
        return cached
    
    query_parts = [
        group.get('drug_name', ''),
        group.get('strain', ''),
        group.get('target_organ', ''),
        'mouse model'
    ]
    query = ' '.join([p for p in query_parts if p]).strip()
    
    if not query:
        return []
    
    try:
        semantic_rate_limiter.wait()
        
        url = f"{Config.SEMANTIC_SCHOLAR_BASE}/paper/search"
        params = {
            'query': query,
            'limit': max_results,
            'fields': 'title,authors,year,abstract,citationCount,venue,publicationDate,externalIds'
        }
        
        response = requests.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        papers = []
        
        for paper in data.get('data', []):
            external_ids = paper.get('externalIds', {})
            doi = external_ids.get('DOI', '')
            pmid = external_ids.get('PubMed', '')
            
            papers.append({
                'title': paper.get('title', ''),
                'authors': ', '.join([a.get('name', '') for a in paper.get('authors', [])[:3]]),
                'year': paper.get('year'),
                'venue': paper.get('venue', ''),
                'citations': paper.get('citationCount', 0),
                'doi': doi,
                'pmid': pmid,
                'url': f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}",
                'source': 'Semantic Scholar'
            })
        
        api_cache.set('semantic_scholar', cache_key, papers)
        return papers
        
    except Exception as e:
        logger.error(f"Semantic Scholar search failed: {e}")
        return []

def search_openalex(group, max_results=5):
    """Search OpenAlex API for papers."""
    cache_key = {
        'drug': group.get('drug_name', ''),
        'strain': group.get('strain', ''),
        'target': group.get('target_organ', ''),
        'max': max_results
    }
    
    cached = api_cache.get('openalex', cache_key)
    if cached:
        return cached
    
    query_parts = [
        group.get('drug_name', ''),
        group.get('strain', ''),
        group.get('target_organ', ''),
        'mouse'
    ]
    query = ' '.join([p for p in query_parts if p]).strip()
    
    if not query:
        return []
    
    try:
        openalex_rate_limiter.wait()
        
        url = f"{Config.OPENALEX_BASE}/works"
        params = {
            'search': query,
            'filter': 'type:journal-article',
            'per-page': max_results,
            'mailto': 'research@example.com'  # Polite pool access
        }
        
        response = requests.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        papers = []
        
        for work in data.get('results', []):
            papers.append({
                'title': work.get('title', ''),
                'authors': ', '.join([a.get('author', {}).get('display_name', '')
                                     for a in work.get('authorships', [])[:3]]),
                'year': work.get('publication_year'),
                'venue': work.get('primary_location', {}).get('source', {}).get('display_name', ''),
                'citations': work.get('cited_by_count', 0),
                'doi': work.get('doi', '').replace('https://doi.org/', ''),
                'url': work.get('doi', work.get('id', '')),
                'source': 'OpenAlex'
            })
        
        api_cache.set('openalex', cache_key, papers)
        return papers
        
    except Exception as e:
        logger.error(f"OpenAlex search failed: {e}")
        return []

def search_crossref(group, max_results=5):
    """Search CrossRef API for papers."""
    cache_key = {
        'drug': group.get('drug_name', ''),
        'strain': group.get('strain', ''),
        'target': group.get('target_organ', ''),
        'max': max_results
    }
    
    cached = api_cache.get('crossref', cache_key)
    if cached:
        return cached
    
    query_parts = [
        group.get('drug_name', ''),
        group.get('strain', ''),
        group.get('target_organ', ''),
        'mouse study'
    ]
    query = ' '.join([p for p in query_parts if p]).strip()
    
    if not query:
        return []
    
    try:
        url = Config.CROSSREF_BASE
        params = {
            'query': query,
            'rows': max_results,
            'filter': 'type:journal-article',
            'mailto': 'research@example.com'
        }
        
        response = requests.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        papers = []
        
        for item in data.get('message', {}).get('items', []):
            # Extract authors
            authors = []
            for author in item.get('author', [])[:3]:
                given = author.get('given', '')
                family = author.get('family', '')
                authors.append(f"{given} {family}".strip())
            
            # Extract publication date
            pub_date = item.get('published-print', item.get('published-online', {}))
            year = pub_date.get('date-parts', [[None]])[0][0] if pub_date else None
            
            papers.append({
                'title': item.get('title', [''])[0],
                'authors': ', '.join(authors),
                'year': year,
                'venue': item.get('container-title', [''])[0],
                'doi': item.get('DOI', ''),
                'url': f"https://doi.org/{item.get('DOI', '')}",
                'source': 'CrossRef'
            })
        
        api_cache.set('crossref', cache_key, papers)
        return papers
        
    except Exception as e:
        logger.error(f"CrossRef search failed: {e}")
        return []

# [Previous NCBI, Europe PMC, and IMPC functions remain the same]

def get_drug_data_from_ncbi(drug_name):
    """Get PubChem CID and build compound URL."""
    if not drug_name:
        return {"success": False, "error": "Drug name is required."}

    # Normalise: trim surrounding whitespace so a stray trailing space does not
    # turn a valid name into a 404 (e.g. "ibuprofen " -> ".../ibuprofen%20/...").
    drug_name = drug_name.strip()
    if not drug_name:
        return {"success": False, "error": "Drug name is required."}

    if drug_name.lower() in ['saline', 'control', 'pbs', 'vehicle']:
        return {"success": True, "ncbi_link": "#", "is_control": True}

    cache_key = {'drug_name': drug_name.lower()}
    cached = api_cache.get('pubchem', cache_key)
    if cached:
        return cached

    try:
        # URL-encode the name so spaces/special characters don't break the URL.
        encoded = requests.utils.quote(drug_name, safe='')
        url = f"{Config.PUBCHEM_API_BASE}/compound/name/{encoded}/cids/JSON"
        response = requests.get(url, timeout=Config.REQUEST_TIMEOUT)

        # 404 = the drug name is genuinely not in PubChem (often a typo),
        # NOT a connectivity problem. Give an accurate, actionable message.
        if response.status_code == 404:
            result = {"success": False,
                      "error": f"Drug '{drug_name}' not found in PubChem — please check the spelling."}
            api_cache.set('pubchem', cache_key, result)
            return result

        response.raise_for_status()

        cid_list = response.json().get('IdentifierList', {}).get('CID', [])
        if not cid_list:
            result = {"success": False,
                      "error": f"Drug '{drug_name}' not found in PubChem — please check the spelling."}
        else:
            cid = cid_list[0]
            result = {
                "success": True,
                "ncbi_link": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                "cid": cid
            }

        api_cache.set('pubchem', cache_key, result)
        return result

    except requests.exceptions.HTTPError as e:
        # Any other HTTP status from PubChem (e.g. 400 bad name).
        logger.error(f"PubChem HTTP error for '{drug_name}': {e}")
        return {"success": False,
                "error": f"Drug '{drug_name}' could not be found in PubChem — please check the spelling."}
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        # Genuine connectivity/timeout problem — do NOT cache this.
        logger.error(f"PubChem connection error for '{drug_name}': {e}")
        return {"success": False,
                "error": "PubChem is temporarily unreachable. Please try again in a moment."}
    except Exception as e:
        logger.error(f"PubChem API error for '{drug_name}': {e}")
        return {"success": False, "error": "PubChem lookup failed. Please try again."}

@retry(stop=stop_after_attempt(Config.MAX_RETRIES), wait=wait_exponential(multiplier=1, min=2, max=10))
def _pubmed_search_with_retry(term, max_results):
    """PubMed search with retry logic."""
    ncbi_rate_limiter.wait()
    
    esearch_url = f"{Config.NCBI_API_BASE}/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": max_results
    }
    
    if Config.NCBI_API_KEY:
        params["api_key"] = Config.NCBI_API_KEY
    
    response = requests.get(esearch_url, params=params, timeout=Config.REQUEST_TIMEOUT)
    response.raise_for_status()
    
    data = response.json()
    return data.get("esearchresult", {}).get("idlist", [])

def search_pubmed_articles(group, max_results=5):
    """Search PubMed for relevant articles with caching."""
    cache_key = {
        'drug': group.get("drug_name", ""),
        'strain': group.get("strain", ""),
        'target': group.get("target_organ", ""),
        'max': max_results
    }
    
    cached = api_cache.get('pubmed_search', cache_key)
    if cached:
        return cached
    
    parts_full = [
        group.get("drug_name", ""),
        group.get("strain", ""),
        group.get("target_organ", ""),
        "mouse[Title/Abstract] OR mice[Title/Abstract]"
    ]
    term_full = " ".join([p for p in parts_full if p]).strip()
    
    if not term_full:
        return []
    
    try:
        pmids = _pubmed_search_with_retry(term_full, max_results)
        
        if not pmids:
            api_cache.set('pubmed_search', cache_key, [])
            return []
        
        ncbi_rate_limiter.wait()
        esummary_url = f"{Config.NCBI_API_BASE}/esummary.fcgi"
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json"
        }
        
        if Config.NCBI_API_KEY:
            params["api_key"] = Config.NCBI_API_KEY
        
        r2 = requests.get(esummary_url, params=params, timeout=Config.REQUEST_TIMEOUT)
        r2.raise_for_status()
        data2 = r2.json()
        
        result_block = data2.get("result", {})
        articles = []
        
        for pmid in pmids:
            raw = result_block.get(pmid)
            if not raw:
                continue
            
            pubdate = raw.get("pubdate", "") or raw.get("sortpubdate", "")
            year = pubdate.split(" ")[0] if pubdate else None
            
            articles.append({
                "pmid": pmid,
                "title": raw.get("title", ""),
                "journal": raw.get("fulljournalname", ""),
                "year": year,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source": "PubMed"
            })
        
        api_cache.set('pubmed_search', cache_key, articles)
        return articles
        
    except Exception as e:
        logger.error(f"PubMed search failed: {e}")
        return []

def search_europe_pmc(group, max_results=3):
    """Search Europe PMC for articles."""
    cache_key = {
        'drug': group.get("drug_name", ""),
        'strain': group.get("strain", ""),
        'target': group.get("target_organ", ""),
        'max': max_results
    }
    
    cached = api_cache.get('europe_pmc', cache_key)
    if cached:
        return cached
    
    parts = [
        group.get("drug_name", ""),
        group.get("strain", ""),
        group.get("target_organ", ""),
        "mouse OR mice"
    ]
    query = " ".join([p for p in parts if p]).strip()
    
    if not query:
        return []
    
    try:
        url = f"{Config.EUROPE_PMC_BASE}/search"
        params = {"query": query, "format": "json", "pageSize": max_results}
        
        r = requests.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        
        records = data.get("resultList", {}).get("result", []) or []
        out = []
        
        for rec in records:
            out.append({
                "id": rec.get("id"),
                "source": rec.get("source"),
                "title": rec.get("title", ""),
                "journal": rec.get("journalTitle", ""),
                "year": rec.get("pubYear"),
                "pmid": rec.get("pmid"),
                "url": f"https://europepmc.org/article/{rec.get('source','')}/{rec.get('id','')}",
                "source": "Europe PMC"
            })
        
        api_cache.set('europe_pmc', cache_key, out)
        return out
        
    except Exception as e:
        logger.error(f"Europe PMC search failed: {e}")
        return []

def search_impc(group, max_results=3):
    """Search IMPC for strain phenotype data."""
    strain = group.get('strain', '').replace('/', '%2F')
    target = group.get('target_organ', '').lower()
    
    phenotype_map = {
        'brain': ['nervous system', 'behavior'],
        'heart': ['cardiovascular system'],
        'liver': ['liver', 'metabolism'],
        'kidney': ['renal'],
        'lung': ['respiratory system'],
    }
    
    phenotypes = []
    for key, terms in phenotype_map.items():
        if key in target:
            phenotypes = terms
            break
    
    if not strain or not phenotypes:
        return []
    
    cache_key = {'strain': strain, 'phenotypes': str(phenotypes), 'max': max_results}
    cached = api_cache.get('impc', cache_key)
    if cached:
        return cached
    
    try:
        base_url = f"{Config.IMPC_BASE}/genotype-phenotype/select"
        results = []
        
        for phenotype in phenotypes[:2]:
            params = {
                'q': f'marker_symbol:* AND strain_name:*{strain}* AND top_level_mp_term_name:*{phenotype}*',
                'rows': max_results,
                'wt': 'json'
            }
            
            response = requests.get(base_url, params=params, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            docs = data.get('response', {}).get('docs', [])
            for doc in docs:
                results.append({
                    'strain': doc.get('strain_name'),
                    'gene': doc.get('marker_symbol'),
                    'phenotype': doc.get('mp_term_name'),
                    'parameter': doc.get('parameter_name'),
                    'p_value': doc.get('p_value'),
                    'effect_size': doc.get('effect_size'),
                    'url': f"https://www.mousephenotype.org/data/genes/{doc.get('marker_accession_id', '')}",
                    'source': 'IMPC'
                })
        
        results = results[:max_results]
        api_cache.set('impc', cache_key, results)
        return results
        
    except Exception as e:
        logger.error(f"IMPC search failed: {e}")
        return []

def build_comprehensive_reference_corpus(group):
    """Build comprehensive reference corpus from ALL sources."""
    logger.info(f"Building comprehensive reference corpus for {group.get('drug_name', 'unknown')}")
    
    # Search all APIs CONCURRENTLY so total time ≈ the slowest single call
    # (not the sum). One slow/failing database no longer stalls the request.
    from concurrent.futures import ThreadPoolExecutor
    _tasks = {
        'pubmed':   lambda: search_pubmed_articles(group, max_results=5),
        'europe':   lambda: search_europe_pmc(group, max_results=3),
        'semantic': lambda: search_semantic_scholar(group, max_results=5),
        'openalex': lambda: search_openalex(group, max_results=5),
        'crossref': lambda: search_crossref(group, max_results=3),
        'impc':     lambda: search_impc(group, max_results=3),
    }
    _results = {k: [] for k in _tasks}
    with ThreadPoolExecutor(max_workers=6) as _ex:
        _futs = {_ex.submit(fn): name for name, fn in _tasks.items()}
        for _fut, _name in _futs.items():
            try:
                _results[_name] = _fut.result(timeout=12) or []
            except Exception as e:
                logger.warning(f"{_name} search failed/timeout: {e}")
                _results[_name] = []
    pubmed_refs = _results['pubmed']
    europe_refs = _results['europe']
    semantic_refs = _results['semantic']
    openalex_refs = _results['openalex']
    crossref_refs = _results['crossref']
    impc_refs = _results['impc']
    
    # Combine and deduplicate by title
    all_papers = []
    seen_titles = set()
    
    for paper_list in [pubmed_refs, europe_refs, semantic_refs, openalex_refs, crossref_refs]:
        for paper in paper_list:
            title = paper.get('title', '').lower().strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                all_papers.append(paper)
    
        # Sort by year (most recent first) and citation count
    def safe_int(val):
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    all_papers.sort(
        key=lambda x: (
            safe_int(x.get('year')),
            safe_int(x.get('citations'))
        ),
        reverse=True  # عشان الأحدث والأكثر استشهادًا يجي أول
    )

    
    return {
        "pubmed": pubmed_refs,
        "europe_pmc": europe_refs,
        "semantic_scholar": semantic_refs,
        "openalex": openalex_refs,
        "crossref": crossref_refs,
        "impc": impc_refs,
        "all_papers": all_papers[:15]  # Top 15 papers
    }

# ============================================================================
# STATISTICAL FUNCTIONS
# ============================================================================

def calculate_sample_size_power_analysis(
    effect_size: float,
    alpha: float = 0.05,
    power: float = 0.80,
    sd: float = None,
    mean_diff: float = None
) -> dict:
    """Statistical power analysis for sample size determination."""
    try:
        if mean_diff is not None and sd is not None and sd > 0:
            effect_size = abs(mean_diff) / sd
        
        if effect_size <= 0:
            effect_size = 0.5
        
        n_per_group = tt_ind_solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power,
            ratio=1.0,
            alternative='two-sided'
        )
        
        n_per_group_rounded = int(np.ceil(n_per_group))
        n_with_attrition = int(np.ceil(n_per_group_rounded * 1.10))
        
        achieved_power = tt_ind_solve_power(
            effect_size=effect_size,
            alpha=alpha,
            nobs1=n_per_group_rounded,
            ratio=1.0,
            alternative='two-sided'
        )
        
        return {
            "success": True,
            "n_per_group": n_per_group_rounded,
            "n_with_10pct_attrition": n_with_attrition,
            "requested_power": power,
            "achieved_power": round(achieved_power, 3),
            "alpha": alpha,
            "effect_size": round(effect_size, 3),
            "method": "Two-sample t-test power analysis"
        }
    except Exception as e:
        logger.error(f"Power analysis failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "n_per_group": 10
        }

def generate_power_curve_data(effect_size, alpha=0.05):
    """Generate data for power curve visualization."""
    sample_sizes = np.arange(5, 31, 1)
    powers = []
    
    for n in sample_sizes:
        try:
            power = tt_ind_solve_power(
                effect_size=effect_size,
                alpha=alpha,
                nobs1=n,
                ratio=1.0,
                alternative='two-sided'
            )
            powers.append(power)
        except:
            powers.append(0.5)
    
    return sample_sizes.tolist(), powers

# ============================================================================
# SAMPLE TYPES & UTILITIES
# ============================================================================

SAMPLE_TYPES = [
    "Blood (whole blood)", "Blood (plasma)", "Blood (serum)",
    "Brain tissue", "Heart tissue", "Liver tissue", "Kidney tissue",
    "Lung tissue", "Spleen tissue", "Muscle tissue", "Bone tissue",
    "Bone marrow", "Adipose tissue", "Pancreatic tissue",
    "Intestinal tissue", "Skin tissue", "Tumor tissue",
    "Cerebrospinal fluid (CSF)", "Urine", "Feces", "Other"
]

def parse_float_safe(value, default=0.0):
    """Safely parse float values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def parse_int_safe(value, default=0):
    """Safely parse integer values."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def recommend_statistical_test(num_groups: int, repeated_measures: bool = False) -> dict:
    """Recommend appropriate statistical test."""
    recommendations = {
        "test": "",
        "assumptions": [],
        "software": [],
        "post_hoc": ""
    }
    
    if num_groups == 2:
        if repeated_measures:
            recommendations["test"] = "Paired t-test"
            recommendations["assumptions"] = [
                "Paired observations",
                "Normally distributed differences"
            ]
            recommendations["software"] = ["R: t.test(paired=TRUE)", "Python: scipy.stats.ttest_rel"]
        else:
            recommendations["test"] = "Independent samples t-test"
            recommendations["assumptions"] = [
                "Independent groups",
                "Normal distribution",
                "Equal variances"
            ]
            recommendations["software"] = ["R: t.test()", "Python: scipy.stats.ttest_ind"]
    else:
        recommendations["test"] = "One-way ANOVA"
        recommendations["assumptions"] = [
            "Independent groups",
            "Normal distribution",
            "Homogeneity of variances"
        ]
        recommendations["software"] = ["R: aov()", "Python: scipy.stats.f_oneway"]
        recommendations["post_hoc"] = "Tukey HSD or Bonferroni"
    
    return recommendations


def get_compound_summary(drug_name, cid=None):
    """A brief plain-language description of the compound from PubChem (cached),
    with a citable reference URL. Used to give the researcher a quick overview."""
    ck = {'drug': (drug_name or '').lower(), 'type': 'desc'}
    cached = api_cache.get('pubchem_desc', ck)
    if cached:
        return cached
    result = {'description': '', 'reference_url': ''}
    try:
        if cid is None:
            cd = get_drug_data_from_ncbi(drug_name)
            cid = cd.get('cid') if cd.get('success') else None
        if not cid:
            return result
        result['reference_url'] = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        r = requests.get(f"{Config.PUBCHEM_API_BASE}/compound/cid/{cid}/description/JSON", timeout=8)
        if r.status_code == 200:
            for info in r.json().get('InformationList', {}).get('Information', []):
                if info.get('Description'):
                    result['description'] = info['Description']
                    if info.get('DescriptionURL'):
                        result['reference_url'] = info['DescriptionURL']
                    break
    except Exception as e:
        logger.warning(f"Compound description failed for {drug_name}: {e}")
    if result['description']:
        api_cache.set('pubchem_desc', ck, result)
    return result


def build_protocol_timeline(group, animal_word='mice'):
    """
    Generate a day-by-day experimental protocol as an editable STARTING POINT
    (acclimatize -> baseline -> fast -> dose -> monitor -> sample -> endpoint).
    Concrete day numbers are defaults the researcher can edit.
    """
    dose = group.get('dose', '')
    route = (group.get('route', 'Oral') or 'Oral')
    diet = (group.get('diet_type', 'Standard') or 'Standard')
    samples = group.get('sample_types', []) or []
    sample_str = ', '.join(samples) if samples else 'blood/tissue as required'
    is_control = (group.get('drug_name', '') or '').lower() in ['saline', 'control', 'pbs', 'vehicle']
    agent = 'vehicle (saline)' if is_control else f"{group.get('drug_name', 'compound')} at {dose} mg/kg"

    steps = [
        {'day': 'Day 1–3', 'phase': 'Acclimatization',
         'activity': f'Allow {animal_word} to acclimatize to the facility. Free access to food and water; daily health checks.'},
        {'day': 'Day 4', 'phase': 'Baseline',
         'activity': 'Record baseline body weight and body condition score; randomize animals into groups.'},
    ]
    if diet.lower() == 'fast':
        steps.append({'day': 'Day 5 (AM)', 'phase': 'Fasting',
                      'activity': 'Fast animals 6–12 h before dosing (water allowed); record pre-dose weight.'})
    steps += [
        {'day': 'Day 5', 'phase': 'Dosing',
         'activity': f'Administer {agent} via {route} route; record time and any immediate reactions.'},
        {'day': 'Day 6–11', 'phase': 'Monitoring',
         'activity': 'Daily monitoring: body weight, clinical signs and humane endpoints (see Toxicity & Humane Endpoints).'},
        {'day': 'Day 12', 'phase': 'Sample collection',
         'activity': f'Collect samples: {sample_str}. Respect safe blood-volume limits.'},
        {'day': 'Day 13', 'phase': 'Endpoint',
         'activity': 'Apply humane endpoint / approved euthanasia method; collect terminal tissues.'},
    ]
    return steps


def biological_advice_for(species, group):
    """Short species-specific husbandry / handling advice."""
    common = [
        'Confirm veterinary consultation and IACUC approval before starting.',
        'Use aseptic technique and appropriate analgesia where procedures may cause pain.',
    ]
    if species == 'Rat':
        return [
            'Rats: house in pairs/groups; provide gnawing/enrichment. ~200–350 g adult.',
            'Oral gavage volume ≤ 10 mL/kg; handle calmly to reduce stress.',
        ] + common
    return [
        'Mice: house in social groups (≤5/cage); provide nesting material. ~20–30 g adult.',
        'Oral gavage volume ≤ 10 mL/kg; minimize handling stress.',
    ] + common


# ============================================================================
# CORE PREDICTION LOGIC
# ============================================================================

def get_prediction_and_suggestion(group, all_groups_count=1):
    """Main prediction logic with ML and comprehensive literature search."""
    drug = group.get('drug_name', '') or ''
    is_control = drug.lower() in ['saline', 'control', 'pbs', 'vehicle']

    # Species-aware wording (Mouse vs Rat) used throughout the output
    species = (group.get('species') or 'Mouse').strip().title()
    if species not in ('Mouse', 'Rat'):
        species = 'Mouse'
    animal_word = 'rats' if species == 'Rat' else 'mice'
    # Standard husbandry reference ranges per species (adult)
    STD_REF = {
        'Mouse': {'weight': '20-30 g', 'age': '6-12 weeks'},
        'Rat':   {'weight': '200-350 g', 'age': '8-14 weeks'},
    }[species]
    
    # Build comprehensive reference corpus from ALL sources
    ref_corpus = build_comprehensive_reference_corpus(group)
    has_refs = len(ref_corpus.get("all_papers", [])) > 0
    
    # Calculate blood quantity if blood samples selected
    blood_calc = BloodQuantityCalculator.calculate_blood_needed(
        sample_types=group.get('sample_types', []),
        weight_g=parse_float_safe(group.get('weight'), 25),
        timepoints=1,
        num_replicates=1
    )

    def build_summary(recommended_range):
        """A clear, simple recommendation summary for the UI."""
        # Real toxicity % from LD50 (experimental first, then model estimate)
        tox_pct = tox_cat = ld50_val = tox_source = None
        if not is_control:
            try:
                info = get_real_ld50_info(drug, route=group.get('route', 'oral'), species=species)
                if info.get('found'):
                    ld50_val = info['ld50_mg_kg']
                    tox_cat = info['category']
                    tox_pct = round(ld50_to_toxicity_percentage(ld50_val), 1)
                    tox_source = info.get('source')  # 'experimental' or 'ml_model'
            except Exception as e:
                logger.warning(f"Summary toxicity lookup failed for {drug}: {e}")

        # Humane endpoints + pain monitoring (IACUC Parts 8 & 11), derived from
        # the toxicity level and dose (for treatment groups only).
        welfare = None
        if not is_control:
            try:
                dose_val = parse_float_safe(group.get('dose'), 0)
                pct_ld50 = (dose_val / ld50_val * 100) if (ld50_val and dose_val) else 0
                risk_proxy = tox_pct if tox_pct is not None else 40
                welfare = toxicity_predictor.generate_welfare_recommendations(
                    risk_proxy, pct_ld50=pct_ld50,
                    target_organ=group.get('target_organ'))
            except Exception as e:
                logger.warning(f"Welfare recommendation failed for {drug}: {e}")
        # Recommended tissues/samples to collect, based on the chosen toxicity
        # endpoints and the target organ.
        _endpoints = group.get('toxicity_endpoints', []) or []
        _organ = (group.get('target_organ') or '').lower()
        rec_samples = []
        _ep_map = {
            'hepatotoxicity': ['Liver tissue', 'Blood (serum)'],
            'nephrotoxicity': ['Kidney tissue', 'Blood (serum)'],
            'cardiotoxicity': ['Heart tissue', 'Blood (plasma)'],
            'neurological':   ['Brain tissue'],
            'histopathology': ['Target-organ tissue'],
        }
        for ep in _endpoints:
            for kw, samps in _ep_map.items():
                if kw in ep.lower():
                    rec_samples += samps
        organ_tissue = {'liver': 'Liver tissue', 'kidney': 'Kidney tissue',
                        'heart': 'Heart tissue', 'brain': 'Brain tissue',
                        'lung': 'Lung tissue', 'spleen': 'Spleen tissue'}.get(_organ)
        if organ_tissue:
            rec_samples.append(organ_tissue)
        if not rec_samples:
            rec_samples = ['Blood (plasma)', 'Target-organ tissue']
        # de-duplicate, preserve order
        recommended_samples = list(dict.fromkeys(rec_samples))

        # Brief compound overview + reference (skip for controls)
        drug_overview = None
        if not is_control:
            try:
                drug_overview = get_compound_summary(drug)
            except Exception as e:
                logger.warning(f"Compound overview failed for {drug}: {e}")

        # Recommended strain by experimental paradigm (common choices in the
        # literature) — a suggestion the researcher can override.
        _paradigm = (group.get('experiment_type') or '').lower()
        _strain_rec = {
            'oncology': 'BALB/c nude or NOD-SCID (immunodeficient, for xenografts)',
            'immunology': 'C57BL/6 or BALB/c',
            'neuroscience': 'C57BL/6',
            'metabolic': 'C57BL/6 (diet-induced) or ob/ob',
            'cardiovascular': 'C57BL/6',
            'toxicology': 'C57BL/6 (mouse) or Sprague-Dawley (rat)',
        }
        recommended_strain = None
        for kw, rec in _strain_rec.items():
            if kw in _paradigm:
                recommended_strain = rec
                break
        if not recommended_strain:
            recommended_strain = 'Sprague-Dawley / Wistar' if species == 'Rat' else 'C57BL/6 (most common)'

        return {
            'species': species,
            'strain': group.get('strain', ''),
            'recommended_strain': recommended_strain,
            'drug_overview': drug_overview,
            'animal_word': animal_word,
            'recommended_samples': recommended_samples,
            'recommended_animals': recommended_range,
            'planned_animals': group.get('num_mice', ''),
            'planned_weight_g': group.get('weight'),
            'planned_age_weeks': group.get('age'),
            'standard_weight': STD_REF['weight'],
            'standard_age': STD_REF['age'],
            'route': group.get('route', ''),
            'diet_type': group.get('diet_type', 'Standard'),
            'experiment_type': group.get('experiment_type', ''),
            'target_organ': group.get('target_organ', 'General'),
            'toxicity_endpoints': group.get('toxicity_endpoints', []),
            'samples': group.get('sample_types', []),
            'blood_volume_ml': blood_calc.get('total_volume_ml') if blood_calc.get('needed') else None,
            'blood_safe': (blood_calc.get('safety_color') == 'green') if blood_calc.get('needed') else None,
            'toxicity_percentage': tox_pct,
            'toxicity_category': tox_cat,
            'ld50_mg_kg': ld50_val,
            'toxicity_source': tox_source,  # experimental vs ml_model (estimate)
            'timeline': build_protocol_timeline(group, animal_word),
            'welfare': welfare,
            'biological_advice': biological_advice_for(species, group),
        }

    if is_control:
        # Add blood warnings for control group too
        warnings = []
        if blood_calc['needed'] and blood_calc['safety_color'] != 'green':
            warnings.append(f"Blood collection: {blood_calc['safety_assessment']}")
        
        return {
            "num_mice": group.get('num_mice', ''),
            "summary": build_summary("Match treatment group"),
            "sample_size_for_group": "Match treatment group",
            "recommended_mice": "Match treatment group",
            "toxicity_risk": 0,
            "rationale": "Control group should match treatment groups.",
            "predicted_outcome": "No pharmacological effect expected.",
            "reference_papers": ref_corpus.get("all_papers", [])[:5],
            "validation_score": 85,
            "warnings": warnings,
            "suggested_corrections": [],
            "statistical_test": recommend_statistical_test(all_groups_count),
            "blood_calculation": blood_calc,  # ✅ NOW INCLUDED FOR CONTROL
            "ml_prediction": None,
            "all_sources": {
                "pubmed_count": len(ref_corpus.get("pubmed", [])),
                "semantic_scholar_count": len(ref_corpus.get("semantic_scholar", [])),
                "openalex_count": len(ref_corpus.get("openalex", [])),
                "crossref_count": len(ref_corpus.get("crossref", [])),
                "total_papers": len(ref_corpus.get("all_papers", []))
            }
        }
    
    # Use ML model for prediction if available
    ml_prediction = None
    if ml_model:
        group['num_groups'] = all_groups_count
        ml_prediction = ml_model.predict_sample_size(group)
        logger.info(f"ML prediction for {drug}: {ml_prediction}")
    
    # ENHANCED: Dynamic sample size calculation based on multiple factors
    base_n = 8  # Base sample size
    
    # Factor 1: Drug type and route adjustments
    route = (group.get('route', '') or '').lower()
    route_multipliers = {
        'iv': 1.2,      # Higher variability in IV dosing
        'ip': 1.1,      # Moderate increase for IP
        'oral': 1.0,    # Standard for oral
        'sc': 1.05,     # Slight increase for SC
        'im': 1.1,      # Moderate for IM
        'icv': 1.3      # Highest variability for ICV
    }
    route_factor = route_multipliers.get(route, 1.0)
    
    # Factor 2: Age-based adjustments
    age = parse_float_safe(group.get('age'), 8)
    if age < 6:  # Young mice - more variability
        age_factor = 1.25
    elif age > 18:  # Old mice - more variability and mortality
        age_factor = 1.3
    else:  # Adult mice - standard
        age_factor = 1.0
    
    # Factor 3: Target organ complexity
    target_organ = (group.get('target_organ', '') or '').lower()
    organ_complexity = {
        'brain': 1.3,      # High variability in neuro studies
        'cns': 1.3,
        'nervous': 1.3,
        'heart': 1.25,     # Cardiac studies need more power
        'cardiovascular': 1.25,
        'liver': 1.15,     # Moderate complexity
        'kidney': 1.2,     # Renal studies variable
        'renal': 1.2,
        'lung': 1.2,       # Respiratory variability
        'metabolic': 1.15,
        'tumor': 1.35,     # Tumor studies highly variable
        'cancer': 1.35
    }
    organ_factor = 1.0
    for key, factor in organ_complexity.items():
        if key in target_organ:
            organ_factor = max(organ_factor, factor)
            break
    
    # Factor 4: Dose-dependent adjustments
    dose = parse_float_safe(group.get('dose'), 0)
    if dose > 0:
        if dose < 1:  # Very low dose - may need more animals to detect effect
            dose_factor = 1.2
        elif dose > 100:  # High dose - more toxicity risk
            dose_factor = 1.15
        else:
            dose_factor = 1.0
    else:
        dose_factor = 1.0
    
    # Factor 5: Sex-based considerations
    sex = (group.get('sex', '') or '').lower()
    if 'mixed' in sex or 'both' in sex:
        sex_factor = 1.4  # Mixed groups need more animals
    else:
        sex_factor = 1.0
    
    # Factor 6: Strain-specific variability
    strain = (group.get('strain', '') or '').lower()
    strain_variability = {
        'c57bl/6': 1.0,    # Standard strain, well-characterized
        'c57': 1.0,
        'balb/c': 1.1,     # Slightly more variable
        'balb': 1.1,
        'nude': 1.2,       # Immunocompromised, more variable
        'scid': 1.25,      # Higher variability
        'nsg': 1.25,
        'outbred': 1.3     # Outbred strains most variable
    }
    strain_factor = 1.0
    for key, factor in strain_variability.items():
        if key in strain:
            strain_factor = factor
            break
    
    # Factor 7: Number of groups (for multiple comparisons)
    if all_groups_count > 4:
        groups_factor = 1.15  # More groups = need more power
    elif all_groups_count > 6:
        groups_factor = 1.25
    else:
        groups_factor = 1.0
    
    # Factor 8: Sample type complexity (if blood collection is risky)
    sample_types = group.get('sample_types', [])
    blood_samples = [s for s in sample_types if 'blood' in s.lower() or 'plasma' in s.lower() or 'serum' in s.lower()]
    if len(blood_samples) > 3:  # Multiple blood assays = plan for attrition
        sample_factor = 1.2
    elif blood_samples:
        sample_factor = 1.1
    else:
        sample_factor = 1.0
    
    # Combine all factors
    total_factor = (route_factor * age_factor * organ_factor * dose_factor *
                   sex_factor * strain_factor * groups_factor * sample_factor)
    
    # Calculate dynamic sample size
    dynamic_n = int(np.ceil(base_n * total_factor))
    
    # Ensure reasonable bounds (6-20 mice per group)
    dynamic_n = max(6, min(20, dynamic_n))
    
    # Power analysis with adjusted effect size
    effect_size = 0.8  # Medium effect size default
    
    # Adjust effect size based on target organ (some effects harder to detect)
    if organ_factor > 1.2:
        effect_size = 0.7  # Smaller effect in complex systems
    
    power_result = calculate_sample_size_power_analysis(
        effect_size=effect_size,
        power=0.80,
        alpha=0.05
    )
    
    suggested_n_power = power_result['n_per_group']
    
    # Combine dynamic calculation with power analysis and ML if available
    if ml_prediction:
        # Average of all three methods
        suggested_n = int((dynamic_n + suggested_n_power + ml_prediction) / 3)
    else:
        # Average of dynamic and power analysis
        suggested_n = int((dynamic_n + suggested_n_power) / 2)
    
    # Final bounds check
    suggested_n = max(6, min(18, suggested_n))
    
    # Generate power curve data
    sample_sizes, powers = generate_power_curve_data(effect_size)
    power_curve = {
        'sample_sizes': sample_sizes,
        'powers': powers,
        'effect_size': effect_size
    }
    
    n_with_attrition = int(suggested_n * 1.1)
    
    # Build comprehensive rationale with factor breakdown
    rationale_parts = []
    rationale_parts.append(f"Recommended sample size: {suggested_n}-{n_with_attrition} {animal_word} per group.")
    rationale_parts.append(f"Based on multi-factor analysis combining power analysis (80% power, α=0.05, effect size={effect_size})")
    
    # Add factor explanations if they significantly affected the calculation
    factor_explanations = []
    if route_factor > 1.05:
        factor_explanations.append(f"{route.upper()} route (×{route_factor:.2f})")
    if age_factor > 1.05:
        if age < 6:
            factor_explanations.append(f"young mice age {age}w (×{age_factor:.2f})")
        else:
            factor_explanations.append(f"aged mice {age}w (×{age_factor:.2f})")
    if organ_factor > 1.05:
        factor_explanations.append(f"{target_organ} study (×{organ_factor:.2f})")
    if sex_factor > 1.05:
        factor_explanations.append(f"mixed sex groups (×{sex_factor:.2f})")
    if strain_factor > 1.05:
        factor_explanations.append(f"{strain} strain variability (×{strain_factor:.2f})")
    if groups_factor > 1.05:
        factor_explanations.append(f"{all_groups_count} groups multiple comparisons (×{groups_factor:.2f})")
    if sample_factor > 1.05:
        factor_explanations.append(f"complex sampling ({len(blood_samples)} blood types) (×{sample_factor:.2f})")
    if dose_factor > 1.05:
        if dose < 1:
            factor_explanations.append(f"low dose {dose} mg/kg (×{dose_factor:.2f})")
        else:
            factor_explanations.append(f"high dose {dose} mg/kg (×{dose_factor:.2f})")
    
    if factor_explanations:
        rationale_parts.append(f" with adjustments for: {', '.join(factor_explanations)}.")
    else:
        rationale_parts.append(".")
    
    if ml_prediction:
        rationale_parts.append(f"ML model prediction: {ml_prediction} {animal_word}.")
        rationale_parts.append(f"Dynamic calculation: {dynamic_n} {animal_word}.")
        rationale_parts.append(f"Final recommendation averages all methods.")
    
    if has_refs:
        rationale_parts.append(f"Found {len(ref_corpus['all_papers'])} relevant papers across multiple databases.")
    
    rationale = " ".join(rationale_parts)
    
    # Validation
    warnings = []
    corrections = []
    score = 70
    
    if len(ref_corpus['all_papers']) > 5:
        score += 15
    elif len(ref_corpus['all_papers']) > 0:
        score += 10
    
    num_mice = parse_int_safe(group.get('num_mice'), 0)
    if num_mice:
        diff = num_mice - suggested_n
        if -1 <= diff <= 1:
            score += 15
        elif abs(diff) > 3:
            warnings.append(f"Sample size differs significantly from recommendation (±{abs(diff)} mice).")
            corrections.append(f"Consider adjusting to {suggested_n}-{n_with_attrition} mice.")
    
    # Blood warnings
    if blood_calc['needed'] and blood_calc['safety_color'] != 'green':
        warnings.append(f"Blood collection: {blood_calc['safety_assessment']}")
    
    score = max(0, min(100, score))
    
        # Blood warnings
    if blood_calc['needed'] and blood_calc['safety_color'] != 'green':
        warnings.append(f"Blood collection: {blood_calc['safety_assessment']}")

    score = max(0, min(100, score))

    # اختر أول ورقة من الكوربس وحاول تبني رابط آمن لها
    all_papers_list = ref_corpus.get('all_papers', [])
    first_paper = all_papers_list[0] if all_papers_list else None
    if first_paper:
        paper_url = (
            first_paper.get('url')
            or first_paper.get('pubmed_url')
            or (f"https://doi.org/{first_paper.get('doi')}" if first_paper.get('doi') else None)
            or "#"
        )
    else:
        paper_url = "#"

    return {
        "num_mice": group.get('num_mice', ''),
        "summary": build_summary(f"{suggested_n}-{n_with_attrition}"),
        "sample_size_for_group": f"{suggested_n}-{n_with_attrition} {animal_word} per group",
        "recommended_mice": f"{suggested_n}-{n_with_attrition}",
        "sample_size_details": power_result,
        "power_curve": power_curve,
        "toxicity_risk": 15,
        "rationale": rationale,
        "predicted_outcome": "Based on statistical power analysis and literature review.",
        "reference_papers": all_papers_list[:10],
        "validation_score": score,
        "warnings": warnings,
        "suggested_corrections": corrections,
        "statistical_test": recommend_statistical_test(all_groups_count),
        "blood_calculation": blood_calc,
        "ml_prediction": ml_prediction,
        "calculation_factors": {
            "base_n": base_n,
            "dynamic_n": dynamic_n,
            "power_analysis_n": suggested_n_power,
            "final_n": suggested_n,
            "factors": {
                "route": {"value": route, "multiplier": route_factor},
                "age": {"value": age, "multiplier": age_factor},
                "organ": {"value": target_organ, "multiplier": organ_factor},
                "dose": {"value": dose, "multiplier": dose_factor},
                "sex": {"value": sex, "multiplier": sex_factor},
                "strain": {"value": strain, "multiplier": strain_factor},
                "groups": {"value": all_groups_count, "multiplier": groups_factor},
                "samples": {"value": len(blood_samples), "multiplier": sample_factor}
            },
            "total_multiplier": total_factor
        },
        "all_sources": {
            "pubmed_count": len(ref_corpus.get("pubmed", [])),
            "europe_pmc_count": len(ref_corpus.get("europe_pmc", [])),
            "semantic_scholar_count": len(ref_corpus.get("semantic_scholar", [])),
            "openalex_count": len(ref_corpus.get("openalex", [])),
            "crossref_count": len(ref_corpus.get("crossref", [])),
            "impc_count": len(ref_corpus.get("impc", [])),
            "total_papers": len(all_papers_list)
        },
        "paper_url": paper_url,
        "source": f"{len(all_papers_list)} papers from multiple sources"
    }

# ============================================================================
# ENHANCED PDF GENERATION WITH DIAGRAMS
# ============================================================================

def create_power_curve_chart(power_curve_data, width=400, height=200):
    """Create power curve chart for PDF."""
    drawing = Drawing(width, height)
    
    chart = HorizontalLineChart()
    chart.x = 50
    chart.y = 50
    chart.height = height - 70
    chart.width = width - 100
    
    sample_sizes = power_curve_data['sample_sizes']
    powers = power_curve_data['powers']
    
    chart.data = [[p * 100 for p in powers]]
    chart.categoryAxis.categoryNames = [str(int(s)) for s in sample_sizes[::3]]
    chart.categoryAxis.labels.boxAnchor = 'n'
    chart.categoryAxis.labels.angle = 45
    chart.categoryAxis.labels.fontSize = 8
    
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 20
    chart.valueAxis.labels.fontSize = 8
    
    chart.lines[0].strokeColor = HexColor('#26a65b')
    chart.lines[0].strokeWidth = 2
    
    # Add 80% power reference line
    line = Line(50, 50 + (height-70)*0.8, width-50, 50 + (height-70)*0.8)
    line.strokeColor = colors.red
    line.strokeWidth = 1
    line.strokeDashArray = [3, 3]
    drawing.add(line)
    
    # Add label
    label = String(width/2, height-20, "Statistical Power vs Sample Size", textAnchor='middle')
    label.fontSize = 10
    label.fontName = 'Helvetica-Bold'
    drawing.add(label)
    
    drawing.add(chart)
    return drawing

def create_timeline_diagram(groups, width=500, height=180):
    """Create visual study timeline with colored phases and dates."""
    drawing = Drawing(width, height)
    
    # Title
    title = String(width/2, height-15, "Study Timeline", textAnchor='middle')
    title.fontSize = 14
    title.fontName = 'Helvetica-Bold'
    title.fillColor = HexColor('#1f8f4e')
    drawing.add(title)
    
    # Timeline configuration
    timeline_y = height/2 + 10
    timeline_start = 40
    timeline_end = width - 40
    timeline_length = timeline_end - timeline_start
    bar_height = 50
    
    # Calculate dates
    start_date = datetime.now()
    
    # Phase definitions (proportional widths with actual dates)
    phases = [
        {'name': 'Phase 1', 'title': 'Acclimation', 'weeks': 2, 'proportion': 0.17, 'color': '#4CAF50', 'start': start_date},
        {'name': 'Phase 2', 'title': 'Baseline', 'weeks': 1, 'proportion': 0.08, 'color': '#2196F3', 'start': start_date + timedelta(weeks=2)},
        {'name': 'Phase 3', 'title': 'Treatment', 'weeks': 6, 'proportion': 0.5, 'color': '#FF9800', 'start': start_date + timedelta(weeks=3)},
        {'name': 'Phase 4', 'title': 'Analysis', 'weeks': 3, 'proportion': 0.25, 'color': '#9C27B0', 'start': start_date + timedelta(weeks=9)}
    ]
    
    # Draw colored phase bars with dates
    current_x = timeline_start
    for phase in phases:
        phase_width = timeline_length * phase['proportion']
        
        # Phase bar
        bar = Rect(current_x, timeline_y - bar_height/2, phase_width, bar_height)
        bar.fillColor = HexColor(phase['color'])
        bar.strokeColor = colors.white
        bar.strokeWidth = 2
        drawing.add(bar)
        
        # Phase name
        label_x = current_x + phase_width/2
        label = String(label_x, timeline_y + 8, phase['title'], textAnchor='middle')
        label.fontSize = 10
        label.fontName = 'Helvetica-Bold'
        label.fillColor = colors.white
        drawing.add(label)
        
        # Duration
        duration = String(label_x, timeline_y - 2, f"{phase['weeks']}w", textAnchor='middle')
        duration.fontSize = 9
        duration.fillColor = colors.white
        drawing.add(duration)
        
        # Start date below bar
        date_str = phase['start'].strftime('%b %d')
        date_label = String(current_x + 2, timeline_y - bar_height/2 - 12, date_str, textAnchor='start')
        date_label.fontSize = 7
        date_label.fillColor = HexColor('#555555')
        drawing.add(date_label)
        
        current_x += phase_width
    
    # End date
    end_date = start_date + timedelta(weeks=12)
    end_label = String(timeline_end - 2, timeline_y - bar_height/2 - 12, end_date.strftime('%b %d'), textAnchor='end')
    end_label.fontSize = 7
    end_label.fillColor = HexColor('#555555')
    drawing.add(end_label)
    
    return drawing

def create_enhanced_timeline_diagram(phases, width=450, height=60):
    """Create a clean, horizontal timeline bar with one phase per group, proportional to duration."""
    drawing = Drawing(width, height)
    
    if not phases:
        # Empty message if no phases
        text = String(width/2, height/2, "No groups defined", textAnchor='middle')
        text.fontSize = 10
        drawing.add(text)
        return drawing
    
    # Timeline configuration
    bar_y = 20
    bar_start_x = 10
    bar_end_x = width - 10
    bar_width = bar_end_x - bar_start_x
    bar_height = 35
    
    # Dynamic phase colors (cycle through colors if more than 4 groups)
    base_colors = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#E91E63', '#00BCD4', '#FF5722', '#9E9E9E']
    
    num_phases = len(phases)
    
    # Calculate total weeks across all phases
    total_weeks = sum([p.get('duration_weeks', 6) for p in phases])
    
    if total_weeks == 0:
        total_weeks = num_phases * 6  # Fallback
    
    # Draw phase bars proportional to their duration
    current_x = bar_start_x
    for idx, phase in enumerate(phases):
        color = base_colors[idx % len(base_colors)]
        
        # Calculate proportional width based on duration
        phase_weeks = phase.get('duration_weeks', 6)
        phase_proportion = phase_weeks / total_weeks
        phase_width = bar_width * phase_proportion
        
        # Draw rectangle
        rect = Rect(current_x, bar_y, phase_width, bar_height)
        rect.fillColor = HexColor(color)
        rect.strokeColor = colors.white
        rect.strokeWidth = 1.5
        drawing.add(rect)
        
        # Add phase number label centered (smaller font for many groups)
        label_x = current_x + phase_width / 2
        label_font_size = 9 if num_phases <= 4 else 7
        label = String(label_x, bar_y + bar_height/2 + 3, f"P{idx + 1}", textAnchor='middle')
        label.fontSize = label_font_size
        label.fontName = 'Helvetica-Bold'
        label.fillColor = colors.white
        drawing.add(label)
        
        # Add duration below label (show actual weeks)
        duration_font_size = 7 if num_phases <= 4 else 6
        duration_label = String(label_x, bar_y + bar_height/2 - 8, f"{phase_weeks}w", textAnchor='middle')
        duration_label.fontSize = duration_font_size
        duration_label.fillColor = colors.white
        drawing.add(duration_label)
        
        current_x += phase_width
    
    return drawing

def create_sample_collection_diagram(blood_calc, width=400, height=200):
    """Create blood collection schedule diagram."""
    drawing = Drawing(width, height)
    
    if not blood_calc['needed']:
        text = String(width/2, height/2, "No blood collection needed", textAnchor='middle')
        text.fontSize = 10
        drawing.add(text)
        return drawing
    
    # Title
    title = String(width/2, height-15, "Blood Collection Schedule", textAnchor='middle')
    title.fontSize = 11
    title.fontName = 'Helvetica-Bold'
    drawing.add(title)
    
    # Visual representation of blood volume
    max_height = 100
    safe_volume = blood_calc['safe_volume_ul']
    needed_volume = blood_calc['total_volume_ul']
    
    # Safe volume bar
    safe_bar_height = max_height
    safe_bar = Rect(100, 30, 60, safe_bar_height)
    safe_bar.fillColor = HexColor('#d1fae5')
    safe_bar.strokeColor = HexColor('#26a65b')
    safe_bar.strokeWidth = 2
    drawing.add(safe_bar)
    
    # Needed volume bar
    needed_bar_height = min(max_height, (needed_volume / safe_volume) * max_height)
    color_map = {'green': '#26a65b', 'orange': '#f59e0b', 'red': '#c82529'}
    needed_color = color_map.get(blood_calc['safety_color'], '#26a65b')
    
    needed_bar = Rect(200, 30, 60, needed_bar_height)
    needed_bar.fillColor = HexColor(needed_color)
    needed_bar.strokeColor = colors.black
    needed_bar.strokeWidth = 1
    drawing.add(needed_bar)
    
    # Labels
    safe_label = String(130, 15, f"Safe: {blood_calc['safe_volume_ml']} mL", textAnchor='middle')
    safe_label.fontSize = 8
    drawing.add(safe_label)
    
    needed_label = String(230, 15, f"Needed: {blood_calc['total_volume_ml']} mL", textAnchor='middle')
    needed_label.fontSize = 8
    drawing.add(needed_label)
    
    return drawing

def generate_enhanced_pdf(study_data):
    """Generate enhanced PDF with backgrounds and optimized to fit on one page."""
    buffer = BytesIO()
    # Optimize margins for better fit
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           topMargin=0.4*inch, bottomMargin=0.4*inch,
                           leftMargin=0.5*inch, rightMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles - more compact
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=HexColor('#26a65b'),  # Green color
        spaceAfter=3,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=HexColor('#666666'),
        alignment=TA_CENTER,
        spaceAfter=2
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=HexColor('#1f8f4e'),  # Dark green
        spaceAfter=3,
        spaceBefore=6,
        fontName='Helvetica-Bold',
        leftIndent=0
    )
    
    # Title section with background - very compact
    story.append(Spacer(1, 0.1*inch))
    
    # Add title with background box
    title_text = study_data.get('study_title', 'Untitled Study')
    title_data = [[Paragraph(f"🐭 {title_text}", title_style)]]
    title_table = Table(title_data, colWidths=[7*inch])
    title_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#e9f8ef')),  # Light green background
        ('BOX', (0, 0), (-1, -1), 2, HexColor('#26a65b')),  # Green border
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(title_table)
    story.append(Spacer(1, 0.05*inch))
    
    # Generated date only (removed "Study Plan Document")
    subtitle_data = [[Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}", subtitle_style)]]
    subtitle_table = Table(subtitle_data, colWidths=[7*inch])
    subtitle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f3f7fa')),  # Light background
        ('BOX', (0, 0), (-1, -1), 1, HexColor('#cfe9dc')),  # Light border
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(subtitle_table)
    story.append(Spacer(1, 0.12*inch))
    
    groups = study_data.get('groups', [])
    
    # Determine start date from groups or use provided date
    start_date_str = study_data.get('study_start_date')
    if not start_date_str or start_date_str == '':
        group_dates = [g.get('start_date') for g in groups if g.get('start_date')]
        if group_dates:
            start_date_str = min(group_dates)
    
    phases = calculate_study_phases(groups, start_date_str)
    
    # Study Information Section with section header in colored box
    header_data = [[Paragraph("📋 Study Information", heading_style)]]
    header_table = Table(header_data, colWidths=[7*inch])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#d4edda')),  # Light green background
        ('BOX', (0, 0), (-1, -1), 1, HexColor('#26a65b')),  # Green border
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.05*inch))
    
    # Calculate total weeks dynamically from phases using the actual calculated durations
    total_weeks = sum([p.get('duration_weeks', 6) for p in phases])
    
    # Get start date
    display_start_date = ''
    if start_date_str:
        try:
            if isinstance(start_date_str, str):
                parsed_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                display_start_date = parsed_date.strftime('%b %d, %Y')
        except:
            display_start_date = ''
    
    if not display_start_date and phases:
        display_start_date = phases[0]['start_date']
    
    info_data = [
        ['Principal Investigator:', study_data.get('pi_name', 'Not specified')],
        ['Institution:', study_data.get('institution', 'Not specified')],
        ['Study Type:', 'Rodent Pharmacology Study'],
        ['Total Duration:', f'{total_weeks} weeks'],
        ['Start Date:', display_start_date if display_start_date else 'TBD']
    ]
    
    # More compact table with enhanced background
    info_table = Table(info_data, colWidths=[2*inch, 5*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#e9f8ef')),  # Light green background
        ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#155724')),  # Dark green labels
        ('TEXTCOLOR', (1, 0), (1, -1), colors.black),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#cfe9dc')),
        ('BOX', (0, 0), (-1, -1), 2, HexColor('#26a65b'))
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 0.1*inch))

    # Editable day-by-day protocol timeline(s)
    timelines = study_data.get('timelines', []) or []
    for tl in timelines:
        steps = tl.get('steps', []) or []
        if not steps:
            continue
        tl_header = [[Paragraph(f"🗓️ Experimental Timeline — {tl.get('group', '')}", heading_style)]]
        tl_header_table = Table(tl_header, colWidths=[7*inch])
        tl_header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#dbeafe')),
            ('BOX', (0, 0), (-1, -1), 1, HexColor('#2563eb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(tl_header_table)
        story.append(Spacer(1, 0.04*inch))

        cell_style = ParagraphStyle('tlcell', fontName='Helvetica', fontSize=8, leading=10)
        head_style = ParagraphStyle('tlhead', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white)
        tl_data = [[Paragraph('Day', head_style), Paragraph('Phase', head_style), Paragraph('Activity', head_style)]]
        for step in steps:
            tl_data.append([
                Paragraph(str(step.get('day', '')), cell_style),
                Paragraph(str(step.get('phase', '')), cell_style),
                Paragraph(str(step.get('activity', '')), cell_style),
            ])
        tl_table = Table(tl_data, colWidths=[0.9*inch, 1.3*inch, 4.8*inch])
        tl_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2563eb')),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#bfdbfe')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(tl_table)
        story.append(Spacer(1, 0.12*inch))

    # Experimental Groups - Detailed Analysis Section
    if groups:
        groups_header_data = [[Paragraph("🧪 Experimental Groups - Detailed Analysis", heading_style)]]
        groups_header_table = Table(groups_header_data, colWidths=[7*inch])
        groups_header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#d4edda')),
            ('BOX', (0, 0), (-1, -1), 1, HexColor('#26a65b')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(groups_header_table)
        story.append(Spacer(1, 0.05*inch))
        
        # Add each group as a detailed table
        for idx, g in enumerate(groups, 1):
            # Group title
            group_title = Paragraph(f"<b>Group {idx}: {g.get('group_name', f'Group {idx}')}</b>",
                                   ParagraphStyle('GroupTitle', parent=styles['Normal'], fontSize=10,
                                                fontName='Helvetica-Bold', textColor=HexColor('#1f8f4e')))
            story.append(group_title)
            story.append(Spacer(1, 0.05*inch))
            
            # Group details table
            group_details = [
                ['Drug Name:', g.get('drug_name', g.get('drug', 'N/A'))],
                ['Dose:', f"{g.get('dose', 'N/A')} mg/kg"],
                ['Strain:', g.get('strain', 'N/A')],
                ['Number of Mice:', str(g.get('num_mice', 'N/A'))],
                ['Route:', g.get('route', 'N/A')],
                ['Target Organ:', g.get('target_organ', 'N/A')],
                ['Start Date:', g.get('start_date', 'TBD')]
            ]
            
            group_table = Table(group_details, colWidths=[2*inch, 5*inch])
            group_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f9fafb')),
                ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#374151')),
                ('TEXTCOLOR', (1, 0), (1, -1), colors.black),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e5e7eb')),
                ('BOX', (0, 0), (-1, -1), 1, HexColor('#9ca3af'))
            ]))
            story.append(group_table)
            
            # Add special instructions if present
            if g.get('instructions'):
                story.append(Spacer(1, 0.05*inch))
                instructions_data = [[Paragraph(f"<b>Special Instructions:</b> {g.get('instructions', '')}",
                                               ParagraphStyle('Instructions', parent=styles['Normal'], fontSize=8))]]
                instructions_table = Table(instructions_data, colWidths=[7*inch])
                instructions_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#fffbeb')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('BOX', (0, 0), (-1, -1), 1, HexColor('#fbbf24'))
                ]))
                story.append(instructions_table)
            
            # Add spacing between groups
            if idx < len(groups):
                story.append(Spacer(1, 0.1*inch))
        
        story.append(Spacer(1, 0.1*inch))
    
    # Add disclaimer at bottom with background
    disclaimer_data = [[Paragraph(
        "⚠️ DISCLAIMER: This is a prototype demonstration tool. Not for actual clinical use. All animal research must comply with institutional guidelines and regulations.",
        ParagraphStyle('Disclaimer', parent=styles['Normal'], fontSize=6,
                      textColor=HexColor('#666666'), alignment=TA_CENTER)
    )]]
    disclaimer_table = Table(disclaimer_data, colWidths=[7*inch])
    disclaimer_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f3f4f6')),
        ('BOX', (0, 0), (-1, -1), 1, HexColor('#d1d5db')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(disclaimer_table)
    
    # Build PDF - keep everything on one page
    doc.build(story)
    buffer.seek(0)
    return buffer

def add_visual_timeline_to_docx(doc, phases):
    """Add visual timeline with colored phases to Word document."""
    doc.add_heading("Visual Timeline", level=1)
    
    # Create timeline table
    timeline_table = doc.add_table(rows=1, cols=len(phases))
    timeline_table.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Phase colors (RGB)
    phase_colors = [
        RGBColor(76, 175, 80),   # Green - Phase 1
        RGBColor(33, 150, 243),  # Blue - Phase 2
        RGBColor(255, 152, 0),   # Orange - Phase 3
        RGBColor(156, 39, 176)   # Purple - Phase 4
    ]
    
    for idx, phase in enumerate(phases):
        cell = timeline_table.rows[0].cells[idx]
        cell.text = f"{phase['name']}\n{phase['duration']}"
        
        # Style the cell
        cell_paragraph = cell.paragraphs[0]
        cell_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Make text bold and white
        for run in cell_paragraph.runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.font.size = Pt(11)
        
        # Add background color
        if idx < len(phase_colors):
            shading_elm = OxmlElement('w:shd')
            shading_elm.set(qn('w:fill'), '%02x%02x%02x' % phase_colors[idx])
            cell._element.get_or_add_tcPr().append(shading_elm)
    
    doc.add_paragraph()

def add_protocol_timelines_to_docx(doc, timelines):
    """Render the editable day-by-day protocol timeline(s) into the Word doc."""
    if not timelines:
        return
    doc.add_heading("Experimental Timeline / Study Plan", level=1)
    for tl in timelines:
        steps = tl.get('steps', []) or []
        if not steps:
            continue
        gname = tl.get('group', '')
        if gname:
            p = doc.add_paragraph()
            r = p.add_run(gname)
            r.font.bold = True
            r.font.size = Pt(12)
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Light Grid Accent 1'
        hdr = table.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text = 'Day', 'Phase', 'Activity'
        for c in hdr:
            if c.paragraphs[0].runs:
                c.paragraphs[0].runs[0].font.bold = True
        for step in steps:
            row = table.add_row().cells
            row[0].text = str(step.get('day', ''))
            row[1].text = str(step.get('phase', ''))
            row[2].text = str(step.get('activity', ''))
        doc.add_paragraph()


def add_study_phases_to_docx(doc, phases):
    """Add detailed study phases breakdown to Word document - one phase per group."""
    doc.add_heading("Study Phases", level=1)
    
    # Dynamic phase colors (cycle through colors if more groups)
    base_colors = [
        RGBColor(76, 175, 80),   # Green
        RGBColor(33, 150, 243),  # Blue
        RGBColor(255, 152, 0),   # Orange
        RGBColor(156, 39, 176),  # Purple
        RGBColor(233, 30, 99),   # Pink
        RGBColor(0, 188, 212),   # Cyan
        RGBColor(255, 87, 34),   # Deep Orange
        RGBColor(158, 158, 158)  # Grey
    ]
    
    for idx, phase in enumerate(phases):
        # Get color (cycle if more than 8 groups)
        color_idx = idx % len(base_colors)
        phase_color = base_colors[color_idx]
        
        # Phase heading with bullet
        phase_para = doc.add_paragraph()
        phase_run = phase_para.add_run(f"● {phase['name']}: {phase['title']}")
        phase_run.font.size = Pt(14)
        phase_run.font.bold = True
        phase_run.font.color.rgb = phase_color
        
        # Phase details
        details_para = doc.add_paragraph()
        details_para.paragraph_format.left_indent = Pt(20)
        
        # Build details text
        details_text = f"""Duration: {phase['duration']}
Start: {phase['start_date']}
End: {phase['end_date']}"""
        
        # Add group specifics if available
        if phase.get('dose') or phase.get('route') or phase.get('num_mice'):
            details_text += "\n\nGroup Details:"
            if phase.get('dose'):
                details_text += f"\nDose: {phase['dose']} mg/kg"
            if phase.get('route'):
                details_text += f"\nRoute: {phase['route']}"
            if phase.get('num_mice'):
                details_text += f"\nSample Size: {phase['num_mice']} mice"
        
        # Only add instructions if not empty
        if phase.get('description', '').strip():
            details_text += f"\n\nInstructions:\n{phase['description']}"
        
        details_para.add_run(details_text)
        
        # Add left border color
        pPr = details_para._element.get_or_add_pPr()
        pBdr = OxmlElement('w:pBdr')
        left = OxmlElement('w:left')
        left.set(qn('w:val'), 'single')
        left.set(qn('w:sz'), '24')  # Border width
        left.set(qn('w:space'), '4')
        color = '%02x%02x%02x' % phase_color
        left.set(qn('w:color'), color)
        pBdr.append(left)
        pPr.append(pBdr)
        
        doc.add_paragraph()

def calculate_study_phases(groups, study_start_date=None):
    """Calculate study phases - ONE PHASE PER GROUP directly linked to group data."""
    if not groups:
        return []
    
    phases = []
    
    # Create one phase for each group
    for idx, group in enumerate(groups, 1):
        group_name = group.get('group_name', f'Group {idx}')
        drug_name = group.get('drug_name', 'Unknown')
        instructions = group.get('instructions', '').strip()
        
        # Get group start and end dates from the group data
        group_start_date = group.get('start_date', '')
        group_end_date = group.get('end_date', '')
        
        # Calculate duration and format dates
        if group_start_date and group_end_date:
            try:
                start_dt = datetime.strptime(group_start_date, '%Y-%m-%d')
                end_dt = datetime.strptime(group_end_date, '%Y-%m-%d')
                
                # Calculate actual duration in weeks
                duration_days = (end_dt - start_dt).days
                duration_weeks = max(1, round(duration_days / 7))  # At least 1 week
                
                start_formatted = start_dt.strftime('%b %d, %Y')
                end_formatted = end_dt.strftime('%b %d, %Y')
                
            except Exception as e:
                logger.warning(f"Date parsing error for group {idx}: {e}")
                start_formatted = 'TBD'
                end_formatted = 'TBD'
                duration_weeks = 6
        elif group_start_date:
            # Only start date provided, use default 6 weeks
            try:
                start_dt = datetime.strptime(group_start_date, '%Y-%m-%d')
                start_formatted = start_dt.strftime('%b %d, %Y')
                
                duration_weeks = 6
                end_dt = start_dt + timedelta(weeks=duration_weeks)
                end_formatted = end_dt.strftime('%b %d, %Y')
                
            except Exception as e:
                logger.warning(f"Date parsing error for group {idx}: {e}")
                start_formatted = 'TBD'
                end_formatted = 'TBD'
                duration_weeks = 6
        else:
            # No dates provided
            start_formatted = 'TBD'
            end_formatted = 'TBD'
            duration_weeks = 6
        
        # Create phase directly from group
        phase = {
            'name': f'Phase {idx}',
            'title': f'{group_name} - {drug_name}',
            'duration': f'{duration_weeks} weeks',
            'duration_weeks': duration_weeks,  # Store numeric value for calculations
            'start_date': start_formatted,
            'end_date': end_formatted,
            'description': instructions,
            'group_id': idx,
            'dose': group.get('dose', ''),
            'route': group.get('route', ''),
            'num_mice': group.get('num_mice', '')
        }
        
        phases.append(phase)
    
    return phases

def generate_enhanced_docx(study_data):
    """Generate enhanced Word document matching the study plan format."""
    doc = Document()
    
    # Title
    title = doc.add_heading(study_data.get('study_title', 'Untitled Study'), level=0)
    title_run = title.runs[0]
    title_run.font.size = Pt(22)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Subtitle
    subtitle_para = doc.add_paragraph("Study Plan Document")
    subtitle_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_run = subtitle_para.runs[0]
    subtitle_run.font.size = Pt(10)
    subtitle_run.font.color.rgb = RGBColor(128, 128, 128)
    
    # Generated date
    date_para = doc.add_paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}")
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_run = date_para.runs[0]
    date_run.font.size = Pt(10)
    date_run.font.color.rgb = RGBColor(128, 128, 128)
    
    doc.add_paragraph()
    
    # Calculate study phases
    groups = study_data.get('groups', [])
    start_date = study_data.get('study_start_date', None)
    phases = calculate_study_phases(groups, start_date)
    
    # Calculate total weeks dynamically from phases using the actual calculated durations
    total_weeks = sum([p.get('duration_weeks', 6) for p in phases])
    
    # Study Information Section (with green background)
    doc.add_heading("Study Information", level=1)
    
    info_table = doc.add_table(rows=5, cols=2)
    info_table.style = 'Light Grid'
    
    info_data = [
        ['Principal Investigator:', study_data.get('pi_name', 'Not specified')],
        ['Institution:', study_data.get('institution', 'Not specified')],
        ['Study Type:', 'Rodent Pharmacology Study'],
        ['Total Duration:', f'{total_weeks} weeks'],
        ['Start Date:', phases[0]['start_date'] if phases else 'TBD']
    ]
    
    for i, (label, value) in enumerate(info_data):
        info_table.rows[i].cells[0].text = label
        info_table.rows[i].cells[1].text = value

        # Make labels bold
        info_table.rows[i].cells[0].paragraphs[0].runs[0].font.bold = True

        # Add green background to all cells
        for cell in info_table.rows[i].cells:
            shading_elm = OxmlElement('w:shd')
            shading_elm.set(qn('w:fill'), 'd4edda')  # Light green
            cell._element.get_or_add_tcPr().append(shading_elm)

    # Editable day-by-day protocol timeline (from the results / user edits)
    doc.add_paragraph()
    add_protocol_timelines_to_docx(doc, study_data.get('timelines', []))
    
    doc.add_paragraph()
    
    doc.add_paragraph()
    
    # Disclaimer
    disclaimer_para = doc.add_paragraph(
        "⚠️ Research Protocol: This document is for planning purposes only. "
        "Always consult with qualified researchers and obtain proper ethical approvals."
    )
    disclaimer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    disclaimer_run = disclaimer_para.runs[0]
    disclaimer_run.font.size = Pt(8)
    disclaimer_run.font.color.rgb = RGBColor(128, 128, 128)
    
    # Page 2: Detailed Group Information
    if groups:
        doc.add_page_break()
        doc.add_heading("🧪 Experimental Groups - Detailed Analysis", level=1)
        
        for idx, g in enumerate(groups, 1):
            doc.add_heading(f"Group {idx}: {g.get('group_name', '')}", level=2)
            
            # Group details table
            group_table = doc.add_table(rows=8, cols=2)
            group_table.style = 'Light List Accent 1'
            
            details = [
                ["Drug Name", g.get('drug_name', g.get('drug', ''))],
                ["Dose", f"{g.get('dose', '')} mg/kg"],
                ["Strain", g.get('strain', '')],
                ["Number of Mice", g.get('num_mice', '')],
                ["Route", g.get('route', '')],
                ["Target Organ", g.get('target_organ', '')],
                ["Start Date", g.get('start_date', 'TBD')]
            ]
            
            for i, (label, value) in enumerate(details):
                group_table.rows[i].cells[0].text = label
                group_table.rows[i].cells[1].text = str(value)
                group_table.rows[i].cells[0].paragraphs[0].runs[0].font.bold = True
            
            # Add instructions in merged row if present
            if g.get('instructions'):
                group_table.rows[7].cells[0].text = "Special Instructions"
                group_table.rows[7].cells[0].paragraphs[0].runs[0].font.bold = True
                group_table.rows[7].cells[1].text = g.get('instructions', '')
                
                # Add light yellow background to instructions
                shading_elm = OxmlElement('w:shd')
                shading_elm.set(qn('w:fill'), 'fffbeb')
                group_table.rows[7].cells[1]._element.get_or_add_tcPr().append(shading_elm)
            
            doc.add_paragraph()
            
            # Blood calculation if needed
            if 'blood_calculation' in g and g['blood_calculation'].get('needed'):
                doc.add_heading("💉 Blood Collection Requirements", level=3)
                
                blood_info = g['blood_calculation']
                blood_para = doc.add_paragraph()
                blood_para.add_run(f"Total Volume Needed: ").bold = True
                blood_para.add_run(f"{blood_info['total_volume_ml']} mL\n")
                blood_para.add_run(f"Safe Volume: ").bold = True
                blood_para.add_run(f"{blood_info['safe_volume_ml']} mL\n")
                blood_para.add_run(f"Safety: ").bold = True
                blood_para.add_run(blood_info['safety_assessment'])
                
                # Add color coding
                safety_color = blood_info.get('safety_color', 'grey')
                if safety_color == 'red':
                    shading_elm = OxmlElement('w:shd')
                    shading_elm.set(qn('w:fill'), 'fee2e2')
                    blood_para._element.get_or_add_pPr().append(shading_elm)
                elif safety_color == 'orange':
                    shading_elm = OxmlElement('w:shd')
                    shading_elm.set(qn('w:fill'), 'fef3c7')
                    blood_para._element.get_or_add_pPr().append(shading_elm)
                elif safety_color == 'green':
                    shading_elm = OxmlElement('w:shd')
                    shading_elm.set(qn('w:fill'), 'd1fae5')
                    blood_para._element.get_or_add_pPr().append(shading_elm)
                
                doc.add_paragraph()
        
        # Literature sources
        if 'all_sources' in g:
            sources = g['all_sources']
            doc.add_heading("📚 Literature Sources", level=3)
            
            sources_table = doc.add_table(rows=7, cols=2)
            sources_table.style = 'Light Grid Accent 1'
            
            source_data = [
                ["Database", "Papers Found"],
                ["PubMed", str(sources.get('pubmed_count', 0))],
                ["Semantic Scholar", str(sources.get('semantic_scholar_count', 0))],
                ["OpenAlex", str(sources.get('openalex_count', 0))],
                ["CrossRef", str(sources.get('crossref_count', 0))],
                ["Europe PMC", str(sources.get('europe_pmc_count', 0))],
                ["IMPC", str(sources.get('impc_count', 0))]
            ]
            
            for i, (label, value) in enumerate(source_data):
                sources_table.rows[i].cells[0].text = label
                sources_table.rows[i].cells[1].text = value
                if i == 0:
                    sources_table.rows[i].cells[0].paragraphs[0].runs[0].font.bold = True
                    sources_table.rows[i].cells[1].paragraphs[0].runs[0].font.bold = True
            
            doc.add_paragraph()
        
        if idx < len(groups):
            doc.add_paragraph()
    
    # Save
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def home():
    """Serve main application page."""
    return render_template('index.html')

@app.route('/demo/sample-types')
def sample_types_demo():
    """Serve sample types demo page."""
    return render_template('sample-types-demo.html')

@app.route('/demo/drug-assessment')
def drug_assessment_demo():
    """Serve drug assessment tool with toxicity & efficacy percentages."""
    try:
        return render_template('drug-assessment.html')
    except:
        # Fallback if template not found
        return """
        <html>
        <body>
            <h1>Drug Assessment Tool</h1>
            <p>Template file not found. Please ensure drug-assessment.html is in the templates/ folder.</p>
            <p>Current working directory files:</p>
            <pre>{}</pre>
            <p><a href="/">Return to Home</a></p>
        </body>
        </html>
        """.format(str(os.listdir('.')))


@app.route('/test/working-example')
def test_working_example():
    """Serve working example with sample types integrated."""
    return render_template('index-working-example.html')


@app.route('/sample-types', methods=['GET'])
def get_sample_types():
    """Return list of available sample types."""
    return jsonify({"sample_types": SAMPLE_TYPES})

@app.route('/apply-samples-to-all', methods=['POST'])
def apply_samples_to_all():
    """Apply selected samples to all groups."""
    try:
        data = request.get_json()
        sample_types = data.get('sample_types', [])
        groups = data.get('groups', [])
        
        # Apply sample types to all groups
        for group in groups:
            group['sample_types'] = sample_types.copy()
        
        return jsonify({
            "success": True,
            "message": f"Applied {len(sample_types)} sample type(s) to {len(groups)} group(s)",
            "groups": groups
        })
    
    except Exception as e:
        logger.exception("Error applying samples to all groups")
        return jsonify({"error": str(e)}), 500

@app.route('/predict', methods=['POST'])
@limiter.limit(Config.RATE_LIMIT_PREDICT) if limiter else lambda f: f
def predict():
    """Main prediction endpoint with enhanced features."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        if VALIDATION_AVAILABLE:
            try:
                validated_data = StudySchema().load(data)
                all_groups = validated_data.get('groups', [])
            except ValidationError as err:
                return jsonify({"error": "Validation failed", "details": err.messages}), 400
        else:
            all_groups = data.get('groups', [])
        
        if not all_groups:
            return jsonify({"error": "No groups provided"}), 400
        
        results = []
        all_groups_count = len(all_groups)
        
        for group in all_groups:
            ncbi = get_drug_data_from_ncbi(group.get('drug_name', ''))
            
            if not ncbi['success'] and not ncbi.get('is_control'):
                results.append({
                    "group_name": group.get('group_name', 'Group'),
                    "error": ncbi['error']
                })
                continue
            
            suggestion = get_prediction_and_suggestion(group, all_groups_count)
            
            results.append({
                "group_name": group.get('group_name', 'Group'),
                "drug": (group.get('drug_name') or '').capitalize(),
                "ncbi_link": ncbi.get('ncbi_link', '#'),
                **suggestion
            })
        
        return jsonify(results)
    
    except Exception as e:
        logger.exception("Error in predict endpoint")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route('/study-plan/pdf', methods=['POST'])
def study_plan_pdf():
    """Generate enhanced PDF with diagrams."""
    try:
        data = request.get_json() or {}
        buffer = generate_enhanced_pdf(data)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name="enhanced_study_plan.pdf",
            mimetype="application/pdf"
        )
    
    except Exception as e:
        logger.exception("Error generating PDF")
        return jsonify({"error": "PDF generation failed", "details": str(e)}), 500


@app.route('/study-plan/docx', methods=['POST'])
def study_plan_docx():
    """Generate enhanced Word document."""
    try:
        data = request.get_json() or {}
        buffer = generate_enhanced_docx(data)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name="enhanced_study_plan.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    
    except Exception as e:
        logger.exception("Error generating DOCX")
        return jsonify({"error": "DOCX generation failed", "details": str(e)}), 500

@app.route('/calculate-blood', methods=['POST'])
def calculate_blood():
    """Calculate blood quantity requirements."""
    try:
        data = request.get_json()
        
        result = BloodQuantityCalculator.calculate_blood_needed(
            sample_types=data.get('sample_types', []),
            weight_g=data.get('weight', 25),
            timepoints=data.get('timepoints', 1),
            num_replicates=data.get('replicates', 1)
        )
        
        return jsonify(result)
    
    except Exception as e:
        logger.exception("Error calculating blood quantity")
        return jsonify({"error": str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.exception("Internal server error")
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Rate limit exceeded"}), 429


# ============================================================================
# TOXICITY & EFFECTIVENESS PREDICTION ROUTES
# ============================================================================

@app.route('/predict-toxicity', methods=['POST'])
def predict_toxicity():
    """Endpoint for toxicity prediction with mouse-specific parameters."""
    try:
        data = request.get_json()
        
        drug_name = data.get('drug_name')
        route = data.get('route', 'oral')
        target_organ = data.get('target_organ')
        weight = data.get('weight', 25)
        age = data.get('age', 8)
        dose = data.get('dose', 10)
        
        if not drug_name:
            return jsonify({'error': 'drug_name is required'}), 400
        
        result = toxicity_predictor.predict_toxicity_comprehensive(
            drug_name, route, target_organ, weight, age, dose
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.exception("Error in predict-toxicity endpoint")
        return jsonify({'error': str(e)}), 500


@app.route('/predict-effectiveness', methods=['POST'])
def predict_effectiveness():
    """Endpoint for effectiveness prediction with mouse-specific parameters."""
    try:
        data = request.get_json()
        
        drug_name = data.get('drug_name')
        condition = data.get('condition')
        target_organ = data.get('target_organ')
        weight = data.get('weight', 25)
        age = data.get('age', 8)
        dose = data.get('dose', 10)
        route = data.get('route', 'oral')
        
        if not drug_name:
            return jsonify({'error': 'drug_name is required'}), 400
        
        result = effectiveness_predictor.predict_effectiveness_comprehensive(
            drug_name, condition, target_organ, weight, age, dose, route
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.exception("Error in predict-effectiveness endpoint")
        return jsonify({'error': str(e)}), 500


@app.route('/predict-complete', methods=['POST'])
def predict_complete():
    """Endpoint for combined toxicity + effectiveness prediction with mouse parameters."""
    try:
        data = request.get_json()
        
        drug_name = data.get('drug_name')
        route = data.get('route', 'oral')
        target_organ = data.get('target_organ')
        condition = data.get('condition')
        weight = data.get('weight', 25)
        age = data.get('age', 8)
        dose = data.get('dose', 10)
        
        if not drug_name:
            return jsonify({'error': 'drug_name is required'}), 400
        
        # Run both predictions with mouse parameters
        tox_result = toxicity_predictor.predict_toxicity_comprehensive(
            drug_name, route, target_organ, weight, age, dose
        )
        
        eff_result = effectiveness_predictor.predict_effectiveness_comprehensive(
            drug_name, condition, target_organ, weight, age, dose, route
        )
        
        # Generate overall assessment
        if tox_result['success'] and eff_result['success']:
            overall = generate_overall_assessment(tox_result, eff_result)
            feasibility = assess_study_feasibility(tox_result, eff_result)
            
            # Add therapeutic window analysis
            therapeutic_window = calculate_therapeutic_window(tox_result, eff_result, dose)
            
            return jsonify({
                'drug_name': drug_name,
                'toxicity': tox_result,
                'effectiveness': eff_result,
                'overall_assessment': overall,
                'study_feasibility': feasibility,
                'therapeutic_window': therapeutic_window,
                'mouse_parameters': {
                    'weight_g': weight,
                    'age_weeks': age,
                    'dose_mg_kg': dose,
                    'route': route
                },
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'error': 'Prediction failed',
                'toxicity': tox_result,
                'effectiveness': eff_result
            }), 500
        
    except Exception as e:
        logger.exception("Error in predict-complete endpoint")
        return jsonify({'error': str(e)}), 500


@app.route('/analyze-drug-comprehensive', methods=['POST'])
def analyze_drug_comprehensive():
    """
    NEW ENDPOINT - Comprehensive drug analysis with:
    - Toxicity percentage (0-100%) from PubChem
    - Efficacy percentage (0-100%) from literature
    - Mouse-specific modifiers (8 parameters)
    - Risk-benefit assessment
    - Literature integration
    """
    try:
        data = request.get_json()
        
        # Required parameters
        drug_name = data.get('drug_name')
        dose = data.get('dose', 10)
        weight = data.get('weight', 25)
        age = data.get('age', 8)
        sex = data.get('sex', 'Mixed')
        route = data.get('route', 'oral')
        target_organ = data.get('target_organ', 'General')
        diet_type = data.get('diet_type', 'Standard')
        species = data.get('species', 'Mouse')

        if not drug_name:
            return jsonify({'error': 'drug_name is required'}), 400

        # Step 1: Get PubChem drug data
        pubchem_data = get_pubchem_drug_data(drug_name)

        # Step 2: Calculate base toxicity from the REAL LD50 (experimental -> ML),
        # preferring data for the selected species (Mouse/Rat).
        _cid = pubchem_data.get('cid') if isinstance(pubchem_data, dict) else None
        ld50_info = get_real_ld50_info(drug_name, cid=_cid, route=route, species=species)
        if ld50_info.get('found'):
            base_toxicity_score = ld50_to_toxicity_percentage(ld50_info['ld50_mg_kg'])
        else:
            base_toxicity_score = 40.0
        
        # Step 3: Apply mouse-specific modifiers to toxicity
        toxicity_adjusted = apply_mouse_modifiers(
            base_toxicity_score,
            dose, weight, age, sex, route, target_organ, diet_type
        )
        
        # Step 4: Get efficiency score from literature
        efficiency_data = get_drug_efficiency_from_literature(
            drug_name, target_organ, dose, route
        )
        efficiency_score = calculate_efficiency_percentage(efficiency_data)
        
        # Step 5: Apply mouse-specific modifiers to efficiency
        efficiency_adjusted = apply_mouse_modifiers_efficiency(
            efficiency_score,
            dose, weight, age, sex, route, target_organ, diet_type
        )
        
        # Step 6: Retrieve literature from NCBI, EuropePMC
        literature = get_comprehensive_literature(drug_name, target_organ, efficiency_data)

        # Also fetch REAL individual papers (title + link) so the UI can show
        # clickable references, not just search links.
        try:
            _corpus = build_comprehensive_reference_corpus({
                'drug_name': drug_name,
                'target_organ': target_organ if target_organ and target_organ != 'General' else '',
            })
            reference_papers = _corpus.get('all_papers', [])[:8]
        except Exception as e:
            logger.warning(f"Comprehensive reference papers failed for {drug_name}: {e}")
            reference_papers = []
        
        # Step 7: Generate risk-benefit analysis
        risk_benefit = generate_risk_benefit_analysis(
            toxicity_adjusted, efficiency_adjusted, drug_name, target_organ
        )

        # Step 8: Derive IACUC welfare recommendations (humane endpoints + pain
        # monitoring, Parts 8 & 11). The adjusted toxicity % acts as the risk score.
        pct_ld50 = 0
        if ld50_info.get('found') and ld50_info.get('ld50_mg_kg'):
            try:
                pct_ld50 = (float(dose) / float(ld50_info['ld50_mg_kg'])) * 100
            except (TypeError, ValueError, ZeroDivisionError):
                pct_ld50 = 0
        welfare = toxicity_predictor.generate_welfare_recommendations(
            toxicity_adjusted, pct_ld50=pct_ld50, target_organ=target_organ
        )
        
        return jsonify({
            'drug_name': drug_name,
            'toxicity_percentage': round(toxicity_adjusted, 1),
            'efficiency_percentage': round(efficiency_adjusted, 1),
            'toxicity_score': {
                'base_score': round(base_toxicity_score, 1),
                'adjusted_score': round(toxicity_adjusted, 1),
                'interpretation': interpret_toxicity_score(toxicity_adjusted),
                'pubchem_data': pubchem_data,
                'ld50_mg_kg': ld50_info.get('ld50_mg_kg') if ld50_info.get('found') else None,
                'ld50_category': ld50_info.get('category') if ld50_info.get('found') else None,
                'ld50_source': ld50_info.get('source') if ld50_info.get('found') else 'none',
                'ld50_source_detail': ld50_info.get('source_detail', '') if ld50_info.get('found') else ''
            },
            'efficiency_score': {
                'base_score': round(efficiency_score, 1),
                'adjusted_score': round(efficiency_adjusted, 1),
                'interpretation': interpret_efficiency_score(efficiency_adjusted),
                'literature_evidence': efficiency_data.get('evidence_count', 0)
            },
            'mouse_parameters': {
                'compound': drug_name,
                'dose_mg_kg': dose,
                'weight_g': weight,
                'age_weeks': age,
                'sex': sex,
                'route': route,
                'target_organ': target_organ,
                'diet_type': diet_type
            },
            'modifier_summary': generate_modifier_summary(
                dose, weight, age, sex, route, target_organ, diet_type
            ),
            'literature': literature,
            'reference_papers': reference_papers,
            'risk_benefit_analysis': risk_benefit,
            'recommendations': generate_recommendations(toxicity_adjusted, efficiency_adjusted),
            'welfare_recommendations': welfare,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.exception("Error in analyze-drug-comprehensive endpoint")
        return jsonify({'error': str(e), 'details': str(e)}), 500


# ============================================================================
# NEW HELPER FUNCTIONS FOR COMPREHENSIVE DRUG ANALYSIS
# ============================================================================

def get_pubchem_drug_data(drug_name):
    """Fetch drug data from PubChem REST API."""
    try:
        drug_name = (drug_name or '').strip()
        encoded = requests.utils.quote(drug_name, safe='')
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{encoded}/json"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'PC_Compounds' in data and len(data['PC_Compounds']) > 0:
                compound = data['PC_Compounds'][0]
                return {
                    'cid': compound.get('id', {}).get('id', {}).get('cid'),
                    'source': 'PubChem',
                    'success': True
                }
        return {'success': False}
    except Exception as e:
        logger.error(f"Error fetching PubChem data for {drug_name}: {e}")
        return {'success': False}


def ld50_to_toxicity_percentage(ld50_mg_kg):
    """
    Map an LD50 (mg/kg; lower = more toxic) to a 0-100 toxicity percentage.
    Calibrated so: LD50~3 -> ~95%, ~50 -> ~74%, ~500 -> ~56%, ~2000 -> ~46%,
    >5000 -> <40%. Monotonic on a log scale.
    """
    import math
    ld50 = max(0.1, float(ld50_mg_kg))
    pct = 105 - 18 * math.log10(ld50)
    return max(5.0, min(98.0, pct))


def get_real_ld50_info(drug_name, cid=None, route='oral', species='Mouse'):
    """
    Shared helper: return the best real LD50 estimate for a drug using the
    hybrid predictor (experimental data first, trained ML model second).
    Prefers experimental values for the selected species and route.
    Returns dict with ld50_mg_kg, source, category (or found=False).
    """
    try:
        exp = toxicity_predictor.get_experimental_ld50(drug_name, cid=cid, route=route, species=species)
        if exp.get('found'):
            return {
                'found': True,
                'ld50_mg_kg': exp['ld50_mg_kg'],
                'category': exp['category'],
                'source': 'experimental',
                'source_detail': exp.get('source_detail', ''),
            }
        structure = toxicity_predictor.get_chemical_structure(drug_name)
        if structure.get('success'):
            ml = toxicity_predictor.predict_ld50_ml(structure['smiles'])
            if ml:
                return {
                    'found': True,
                    'ld50_mg_kg': ml['ld50_mg_kg'],
                    'category': ml['category'],
                    'source': 'ml_model',
                    'source_detail': ml.get('source_detail', ''),
                }
    except Exception as e:
        logger.error(f"get_real_ld50_info failed for {drug_name}: {e}")
    return {'found': False}


def calculate_toxicity_percentage(pubchem_data, drug_name):
    """
    Toxicity percentage (0-100%) derived from the REAL LD50 value
    (experimental data first, trained ML model second). Higher = more toxic.
    Falls back to a neutral baseline only when no data/model is available.
    """
    try:
        cid = pubchem_data.get('cid') if isinstance(pubchem_data, dict) else None
        info = get_real_ld50_info(drug_name, cid=cid)
        if info.get('found'):
            return ld50_to_toxicity_percentage(info['ld50_mg_kg'])
        return 40.0  # neutral baseline when nothing is known
    except Exception as e:
        logger.error(f"Error calculating toxicity: {e}")
        return 40.0


def apply_mouse_modifiers(base_score, dose, weight, age, sex, route, target_organ, diet_type):
    """Apply mouse-specific modifiers to toxicity score."""
    adjusted_score = base_score
    
    # Dose modifier
    dose_factor = min((dose / 50) * 10, 15)
    adjusted_score += dose_factor
    
    # Weight modifier
    if weight < 20:
        adjusted_score += 8
    elif weight > 35:
        adjusted_score -= 3
    
    # Age modifier
    if age < 4:
        adjusted_score += 10
    elif age > 52:
        adjusted_score += 5
    
    # Sex modifier
    if sex == 'Female':
        adjusted_score += 3
    elif sex == 'Male':
        adjusted_score += 1
    
    # Route modifier
    route_factors = {'Oral': 0, 'IP': 3, 'IV': 8, 'SC': 2, 'IM': 2, 'ICV': 15}
    adjusted_score += route_factors.get(route, 0)
    
    # Organ target modifier
    organ_factors = {'Brain': 10, 'Liver': 8, 'Kidney': 8, 'Heart': 7, 'Lung': 6, 'General': 0}
    adjusted_score += organ_factors.get(target_organ, 0)
    
    # Diet type modifier
    diet_factors = {'Standard': 0, 'High fat': 5, 'Fast': 3}
    adjusted_score += diet_factors.get(diet_type, 0)
    
    return min(adjusted_score, 100)


def apply_mouse_modifiers_efficiency(base_score, dose, weight, age, sex, route, target_organ, diet_type):
    """Apply mouse-specific modifiers to efficiency score."""
    adjusted_score = base_score
    
    if 5 < dose < 100:
        adjusted_score += 10
    elif dose > 150:
        adjusted_score -= 15
    elif dose < 2:
        adjusted_score -= 10
    
    if 20 < weight < 30:
        adjusted_score += 5
    elif weight < 15:
        adjusted_score -= 8
    
    if 6 <= age <= 12:
        adjusted_score += 5
    elif age < 4:
        adjusted_score -= 10
    elif age > 52:
        adjusted_score -= 5
    
    if sex == 'Male':
        adjusted_score += 2
    
    if route == 'Oral':
        adjusted_score -= 3
    elif route == 'IV':
        adjusted_score += 8
    elif route == 'IP':
        adjusted_score += 5
    
    if diet_type == 'High fat':
        adjusted_score -= 5
    
    return min(adjusted_score, 100)


def get_drug_efficiency_from_literature(drug_name, target_organ, dose, route):
    """Retrieve efficiency data from NCBI and EuropePMC."""
    try:
        search_term = f"{drug_name} {target_organ} efficacy mouse"
        
        # NCBI Entrez (retmode=json is required for a JSON response)
        ncbi_url = (f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                    f"?db=pubmed&term={requests.utils.quote(search_term)}&retmax=5&retmode=json")
        pubmed_count = 0
        try:
            response = requests.get(ncbi_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                pubmed_count = int(data.get('esearchresult', {}).get('count', 0))
        except Exception:
            pass
        
        # EuropePMC
        epmce_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={search_term}&pageSize=5&format=json"
        epmce_count = 0
        try:
            epmce_response = requests.get(epmce_url, timeout=10)
            if epmce_response.status_code == 200:
                epmce_data = epmce_response.json()
                epmce_count = epmce_data.get('hitCount', 0)
        except:
            pass
        
        evidence_count = pubmed_count + epmce_count
        
        if evidence_count > 100:
            efficiency = 85
        elif evidence_count > 50:
            efficiency = 75
        elif evidence_count > 20:
            efficiency = 65
        elif evidence_count > 5:
            efficiency = 50
        else:
            efficiency = 30
        
        return {
            'evidence_count': evidence_count,
            'pubmed_count': pubmed_count,
            'epmce_count': epmce_count,
            'base_efficiency': efficiency,
            'search_term': search_term
        }
    except Exception as e:
        logger.error(f"Error getting efficiency from literature: {e}")
        return {'evidence_count': 0, 'base_efficiency': 40}


def calculate_efficiency_percentage(efficiency_data):
    """Calculate efficiency score from literature evidence."""
    return efficiency_data.get('base_efficiency', 40)


def get_comprehensive_literature(drug_name, target_organ, efficiency_data):
    """Retrieve comprehensive literature from multiple sources."""
    try:
        sources = {}
        
        search_term = f"{drug_name} {target_organ} mouse"
        
        sources['NCBI/PubMed'] = {
            'link': f"https://pubmed.ncbi.nlm.nih.gov/?term={search_term.replace(' ', '+')}",
            'count': efficiency_data.get('pubmed_count', 0),
            'description': f'PubMed search for {drug_name}'
        }
        
        sources['EuropePMC'] = {
            'link': f"https://europepmc.org/search?query={search_term.replace(' ', '+')}",
            'count': efficiency_data.get('epmce_count', 0),
            'description': f'EuropePMC search for {drug_name}'
        }
        
        sources['PubChem'] = {
            'link': f"https://pubchem.ncbi.nlm.nih.gov/compound/{drug_name}",
            'description': f'PubChem compound data for {drug_name}'
        }
        
        return sources
    except Exception as e:
        logger.error(f"Error retrieving literature: {e}")
        return {}


def generate_risk_benefit_analysis(toxicity_score, efficiency_score, drug_name, target_organ):
    """Generate risk-benefit analysis."""
    safety_margin = efficiency_score - toxicity_score
    
    if safety_margin > 30:
        profile = "FAVORABLE - High efficacy with low toxicity risk"
    elif safety_margin > 10:
        profile = "ACCEPTABLE - Moderate efficacy with manageable toxicity risk"
    elif safety_margin > -10:
        profile = "CAUTIOUS - Similar toxicity and efficacy scores"
    else:
        profile = "UNFAVORABLE - High toxicity relative to efficacy"
    
    return {
        'safety_margin': round(safety_margin, 1),
        'profile': profile,
        'recommendation': 'Proceed with caution' if safety_margin < 10 else 'Favorable for study'
    }


def generate_modifier_summary(dose, weight, age, sex, route, target_organ, diet_type):
    """Generate a text summary of modifiers."""
    return f"Dose: {dose}mg/kg | Weight: {weight}g | Age: {age}wks | Sex: {sex} | Route: {route} | Target: {target_organ} | Diet: {diet_type}"


def interpret_toxicity_score(score):
    """Interpret toxicity score."""
    if score < 20:
        return "Low toxicity risk"
    elif score < 40:
        return "Mild toxicity risk"
    elif score < 60:
        return "Moderate toxicity risk"
    elif score < 80:
        return "High toxicity risk"
    else:
        return "Very high toxicity risk"


def interpret_efficiency_score(score):
    """Interpret efficiency score."""
    if score < 20:
        return "Minimal experimental evidence"
    elif score < 40:
        return "Limited efficacy evidence"
    elif score < 60:
        return "Moderate efficacy evidence"
    elif score < 80:
        return "Good efficacy evidence"
    else:
        return "Excellent efficacy evidence"


def generate_recommendations(toxicity_score, efficiency_score):
    """Generate recommendations based on scores."""
    recommendations = []
    
    if toxicity_score > 70:
        recommendations.append("⚠️ HIGH TOXICITY: Consider lower starting doses")
        recommendations.append("⚠️ Plan frequent monitoring")
    elif toxicity_score > 50:
        recommendations.append("⚠️ MODERATE TOXICITY: Standard precautions recommended")
    
    if efficiency_score < 30:
        recommendations.append("⚠️ LIMITED EVIDENCE: Recommend preliminary dose-response study")
    
    if efficiency_score > 75 and toxicity_score < 40:
        recommendations.append("✓ FAVORABLE: Good candidate for efficacy studies")
    
    if efficiency_score < 40 and toxicity_score > 60:
        recommendations.append("✗ UNFAVORABLE: Consider alternative compounds")
    
    if not recommendations:
        recommendations.append("✓ Proceed with standard protocols")
    
    return recommendations


@app.route('/test-assessment', methods=['GET'])
def test_assessment():
    """
    Self-test endpoint for drug assessment functionality.
    Tests all prediction endpoints and returns results.
    """
    results = {
        'test_suite': 'Drug Assessment API Tests',
        'timestamp': datetime.now().isoformat(),
        'tests': [],
        'summary': {}
    }
    
    test_cases = [
        {
            'name': 'Toxicity Prediction - Aspirin',
            'endpoint': '/predict-toxicity',
            'payload': {'drug_name': 'Aspirin', 'route': 'oral'}
        },
        {
            'name': 'Effectiveness Prediction - Ibuprofen',
            'endpoint': '/predict-effectiveness',
            'payload': {'drug_name': 'Ibuprofen', 'condition': 'inflammation'}
        },
        {
            'name': 'Complete Assessment - Metformin',
            'endpoint': '/predict-complete',
            'payload': {'drug_name': 'Metformin', 'route': 'oral', 'condition': 'diabetes'}
        },
        {
            'name': 'High Toxicity Drug - Doxorubicin',
            'endpoint': '/predict-complete',
            'payload': {'drug_name': 'Doxorubicin', 'route': 'IV', 'condition': 'cancer'}
        },
        {
            'name': 'Comprehensive Analysis - Aspirin',
            'endpoint': '/analyze-drug-comprehensive',
            'payload': {'drug_name': 'Aspirin', 'dose': 100, 'weight': 25, 'age': 10, 'sex': 'Female', 'route': 'Oral', 'target_organ': 'General', 'diet_type': 'Standard'}
        }
    ]
    
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        test_result = {
            'name': test_case['name'],
            'endpoint': test_case['endpoint'],
            'status': 'unknown',
            'error': None
        }
        
        try:
            with app.test_client() as client:
                response = client.post(
                    test_case['endpoint'],
                    json=test_case['payload'],
                    content_type='application/json'
                )
                
                if response.status_code == 200:
                    test_result['status'] = 'passed'
                    test_result['response_preview'] = str(response.json)[:200] + '...'
                    passed += 1
                else:
                    test_result['status'] = 'failed'
                    test_result['error'] = f"Status code: {response.status_code}"
                    failed += 1
                    
        except Exception as e:
            test_result['status'] = 'error'
            test_result['error'] = str(e)
            failed += 1
        
        results['tests'].append(test_result)
    
    results['summary'] = {
        'total': len(test_cases),
        'passed': passed,
        'failed': failed,
        'success_rate': f"{(passed/len(test_cases)*100):.1f}%"
    }
    
    return jsonify(results)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify app is running."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '3.1 Enhanced',
        'features': {
            'ml_available': ML_AVAILABLE,
            'rdkit_available': RDKIT_AVAILABLE,
            'validation_available': VALIDATION_AVAILABLE,
            'comprehensive_drug_analysis': True
        },
        'endpoints': {
            'home': '/',
            'predict_toxicity': '/predict-toxicity',
            'predict_effectiveness': '/predict-effectiveness',
            'predict_complete': '/predict-complete',
            'analyze_drug_comprehensive': '/analyze-drug-comprehensive (NEW)',
            'test_assessment': '/test-assessment',
            'health': '/health'
        }
    })


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("=" * 70)
    logger.info("Starting Enhanced Rodent Study Planner v3.1")
    logger.info("=" * 70)
    logger.info(f"✓ ML features: {'ENABLED' if ML_AVAILABLE else 'DISABLED'}")
    logger.info(f"✓ Validation: {'ENABLED' if VALIDATION_AVAILABLE else 'DISABLED'}")
    logger.info(f"✓ APIs configured: PubMed, Semantic Scholar, OpenAlex, CrossRef")
    logger.info(f"✓ Blood calculator: ACTIVE")
    logger.info(f"✓ Enhanced PDF/DOCX: ACTIVE (with diagrams)")
    logger.info(f"✓ NEW: Comprehensive Drug Analysis: ACTIVE")
    logger.info(f"  - Toxicity percentage (0-100%) with PubChem")
    logger.info(f"  - Efficacy percentage (0-100%) with literature")
    logger.info(f"  - Mouse-specific modifiers (8 parameters)")
    logger.info(f"  - Risk-benefit assessment")
    logger.info(f"  - Auto-generated recommendations")
    logger.info(f"✓ NEW ENDPOINT: /analyze-drug-comprehensive")
    logger.info("=" * 70)
    logger.info("🚀 Server starting on http://0.0.0.0:5000")
    logger.info("=" * 70)
    
    app.run(
        debug=Config.DEBUG,
        host='0.0.0.0',
        port=5000
    )
