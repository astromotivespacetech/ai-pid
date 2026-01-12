// PI&D Symbol system with runtime fuzzy matching
// All symbols are loaded dynamically from /api/symbols endpoint
console.log('[pid_symbols.js] Loaded fuzzy matcher v2');

let ALL_SYMBOLS = [];  // Full symbol objects from API (for display)
let SYMBOL_NAMES = []; // Just the names (for fuzzy matching)
let SYMBOLS_LOADED = false;

// Light synonym map to nudge common patterns
const SYNONYM_MAP = {
    'ball_valve': 'valve',
    'gate_valve': 'gate_valve',
    'globe_valve': 'valve',
    'check_valve': 'check_valve',
    'control_valve': 'control_valve',
    'pressure_gauge': 'pressure_indicator',
    'pressure_indicator': 'pressure_indicator',
    'temperature_indicator': 'temperature_indicator',
    'temperature_control': 'temperature_control',
    'flow_indicator': 'flow_indicator',
    'flow_control': 'flow_control',
    'level_indicator': 'level_indicator',
    'level_control': 'level_control',
    'heat_exchanger': 'heat_exchanger',
    'condenser': 'heat_exchanger',
    'reboiler': 'heat_exchanger',
    'evaporator': 'heat_exchanger',
    'compressor': 'compressor',
    'blower': 'compressor',
    'pump': 'pump',
    'meter': 'meter',
    'sensor': 'sensor',
    'reactor': 'reactor',
    'vessel': 'vessel',
    'drum': 'vessel',
    'column': 'vessel',
    'knockout': 'separator',
    'separator': 'separator',
    'tank': 'tank',
    'filter': 'filter',
    'strainer': 'filter',
    'controller': 'controller'
};

const STOPWORDS = new Set(['the','a','an','of','and','unit','system','station','main','aux','spare','area','section','line']);

function normalizeName(name) {
    if (!name) return '';
    // Insert spaces before capitals, drop non-alnum to spaces, collapse
    const spaced = name.replace(/([a-z])([A-Z])/g, '$1 $2');
    const cleaned = spaced.toLowerCase().replace(/[^a-z0-9]+/g, ' ');
    const tokens = cleaned.split(' ').filter(t => t && !STOPWORDS.has(t));
    return tokens.join('_');
}

function tokenize(sym) {
    return sym.split('_').filter(Boolean);
}

// Levenshtein distance - measure of string similarity
function levenshteinDistance(str1, str2) {
    // Convert to strings if needed
    if (typeof str1 !== 'string') str1 = String(str1);
    if (typeof str2 !== 'string') str2 = String(str2);
    
    // Safeguard against extremely long strings that could allocate huge arrays
    const MAX_LEN = 1000;
    if (str1.length > MAX_LEN || str2.length > MAX_LEN) {
        return Math.max(str1.length, str2.length);
    }
    
    const len1 = str1.length;
    const len2 = str2.length;
    const matrix = Array(len2 + 1).fill(null).map(() => Array(len1 + 1).fill(0));
    
    for (let i = 0; i <= len1; i++) matrix[0][i] = i;
    for (let j = 0; j <= len2; j++) matrix[j][0] = j;
    
    for (let j = 1; j <= len2; j++) {
        for (let i = 1; i <= len1; i++) {
            const indicator = str1[i - 1] === str2[j - 1] ? 0 : 1;
            matrix[j][i] = Math.min(
                matrix[j][i - 1] + 1,
                matrix[j - 1][i] + 1,
                matrix[j - 1][i - 1] + indicator
            );
        }
    }
    return matrix[len2][len1];
}

// Calculate similarity score (token + edit blended)
function calculateSimilarity(str1, str2) {
    // Convert to strings if needed
    if (typeof str1 !== 'string') str1 = String(str1);
    if (typeof str2 !== 'string') str2 = String(str2);
    
    const maxLen = Math.max(str1.length, str2.length);
    const editScore = maxLen === 0 ? 1 : 1 - (levenshteinDistance(str1, str2) / maxLen);
    const t1 = tokenize(str1);
    const t2 = tokenize(str2);
    const set2 = new Set(t2);
    const tokenHits = t1.filter(t => set2.has(t)).length;
    const tokenScore = t1.length ? tokenHits / t1.length : 0;
    // Weight tokens more to avoid loose matches
    return 0.65 * tokenScore + 0.35 * editScore;
}

// Find best matching symbol from available symbols
function findBestSymbol(nodeName) {
    if (!SYMBOL_NAMES || SYMBOL_NAMES.length === 0) {
        console.warn('No symbols loaded');
        return null;
    }

    const normalized = normalizeName(nodeName);
    if (!normalized) {
        console.warn('Could not normalize node name:', nodeName);
        return null;
    }
    
    // Safeguard: if normalized name is too long, just return null
    if (normalized.length > 500) {
        console.warn('Node name too long after normalization:', normalized.length);
        return null;
    }

    // Exact match wins immediately
    if (SYMBOL_NAMES.includes(normalized)) {
        return normalized;
    }

    // Synonym hint
    const synonym = SYNONYM_MAP[normalized];
    if (synonym && SYMBOL_NAMES.includes(synonym)) {
        return synonym;
    }

    // Score all symbols
    const scores = SYMBOL_NAMES.map(symbol => {
        try {
            const score = calculateSimilarity(normalized, symbol);
            return {
                symbol: String(symbol),  // Ensure symbol is a string
                score: isNaN(score) ? 0 : score
            };
        } catch (e) {
            console.error('Error scoring symbol:', symbol, e);
            return {
                symbol: String(symbol),
                score: 0
            };
        }
    });

    scores.sort((a, b) => b.score - a.score);

    const best = scores[0];
    console.log(`Finding symbol for "${nodeName}" (${normalized})`);
    console.log('Top 3 matches:', scores.slice(0, 3).map(s => `${s.symbol} ${(s.score * 100).toFixed(1)}%`));

    // Require stronger match to avoid bad picks
    if (best && best.score >= 0.4) {
        return String(best.symbol);  // Ensure we return a string
    }
    return null;
}

// Load all symbols from API
async function loadSymbols() {
    if (SYMBOLS_LOADED) {
        return;
    }
    
    try {
        console.log('Loading symbols from API...');
        const response = await fetch('/api/symbols');
        if (!response.ok) {
            console.error('Failed to fetch symbols:', response.status);
            return;
        }
        
        const data = await response.json();
        if (data.success && data.symbols) {
            // Keep full symbol objects for display in symbol library
            ALL_SYMBOLS = data.symbols;
            
            // Extract just the symbol names for fuzzy matching
            // API returns objects with {name, category, path}, convert names to snake_case
            SYMBOL_NAMES = data.symbols.map(sym => {
                if (typeof sym === 'string') {
                    return sym;
                } else if (sym.name) {
                    // Convert title case back to snake_case for matching
                    return sym.name.toLowerCase().replace(/\s+/g, '_');
                }
                return null;
            }).filter(Boolean);
            
            SYMBOLS_LOADED = true;
            console.log(`Loaded ${ALL_SYMBOLS.length} symbols`);
        } else {
            console.error('Invalid symbol data:', data);
        }
    } catch (err) {
        console.error('Failed to load symbols:', err);
    }
}

// Get node style with PNG symbol
async function getNodeStyle(nodeName) {
    console.log(`[getNodeStyle] Called for node: "${nodeName}"`);
    
    // Ensure symbols are loaded
    if (!SYMBOLS_LOADED) {
        console.log('[getNodeStyle] Symbols not loaded yet, calling loadSymbols()...');
        await loadSymbols();
    }
    
    console.log(`[getNodeStyle] Total symbols available: ${SYMBOL_NAMES.length}`);
    
    // Find the best matching symbol
    const bestSymbol = findBestSymbol(nodeName);
    
    const style = {
        label: nodeName,
        width: 60,
        height: 60,
        fontSize: 12,
        color: '#000',
        textValign: 'bottom'
    };
    
    if (bestSymbol) {
        // Use the PNG symbol from the symbols directory
        const symbolPath = `/static/symbols/${bestSymbol}.png`;
        console.log(`[getNodeStyle] Using symbol: ${bestSymbol} (${symbolPath})`);
        style.backgroundImage = symbolPath;
        style.backgroundFit = 'cover';
        style.backgroundRepeat = 'no-repeat';
    } else {
        // Fallback: use a simple colored circle
        console.log(`[getNodeStyle] No symbol found for "${nodeName}", using default`);
        style.backgroundColor = '#9E9E9E';
        style.shape = 'ellipse';
    }
    
    return style;
}

// Export symbol list for UI customizer
async function getAvailableSymbols() {
    console.log(`[getAvailableSymbols] Called. SYMBOLS_LOADED=${SYMBOLS_LOADED}, ALL_SYMBOLS.length=${ALL_SYMBOLS.length}`);
    if (!SYMBOLS_LOADED) {
        console.log('[getAvailableSymbols] Loading symbols...');
        await loadSymbols();
    }
    console.log(`[getAvailableSymbols] Returning ${ALL_SYMBOLS.length} symbols`);
    return ALL_SYMBOLS;
}

// Ensure symbols are loaded on page startup
async function ensureSymbolsLoaded() {
    await loadSymbols();
}
