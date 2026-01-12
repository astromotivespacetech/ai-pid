// Graph visualization using Cytoscape.js

// Save node positions to localStorage
function saveNodePositions(cy) {
    const positions = {};
    cy.nodes().forEach(node => {
        positions[node.id()] = node.position();
    });
    localStorage.setItem('graphNodePositions', JSON.stringify(positions));
}

// Load node positions from localStorage
function loadNodePositions() {
    const saved = localStorage.getItem('graphNodePositions');
    return saved ? JSON.parse(saved) : {};
}

async function initGraphViewer(containerId, nodes, edges) {
    // Ensure custom symbols (if any) are loaded before styling nodes
    if (typeof ensureSymbolsLoaded === 'function') {
        await ensureSymbolsLoaded();
    }

    const container = document.getElementById(containerId);
    if (!container) {
        console.error('Container not found:', containerId);
        return;
    }

    // Prepare elements for Cytoscape
    const elements = [];
    
    // Load saved node positions from localStorage
    const positionsMap = loadNodePositions();
    
    // Add nodes (with async getNodeStyle)
    if (nodes && Array.isArray(nodes)) {
        for (const nodeOrId of nodes) {
            let nodeId, customImageUrl, nodePosition;
            
            // Handle both string IDs and node objects with custom imageUrl and position
            if (typeof nodeOrId === 'string') {
                nodeId = nodeOrId;
                customImageUrl = null;
                nodePosition = null;
            } else if (typeof nodeOrId === 'object' && nodeOrId.id) {
                nodeId = nodeOrId.id;
                customImageUrl = nodeOrId.imageUrl || null;
                nodePosition = nodeOrId.position || null;  // Get position from node object
            } else {
                console.warn('Invalid node format:', nodeOrId);
                continue;
            }
            
            // Use custom imageUrl if provided, otherwise get auto-matched style
            let imageUrl;
            if (customImageUrl) {
                imageUrl = customImageUrl;
            } else {
                const style = await getNodeStyle(nodeId);
                imageUrl = style.backgroundImage;
            }
            
            // Create node with PNG image URL stored in data so we can access it in stylesheet
            const nodeData = { 
                id: nodeId, 
                label: nodeId,
                imageUrl: imageUrl  // Store PNG image URL in data
            };
            
            const nodeElement = { data: nodeData };
            
            // Add position - prioritize position from node object, then check localStorage
            if (nodePosition) {
                nodeElement.position = nodePosition;
            } else if (positionsMap[nodeId]) {
                nodeElement.position = positionsMap[nodeId];
            }
            
            elements.push(nodeElement);
        }
    }
    
    // Add edges
    if (edges && Array.isArray(edges)) {
        edges.forEach((edge, idx) => {
            let source, target;
            if (Array.isArray(edge)) {
                [source, target] = edge;
            } else if (typeof edge === 'object') {
                source = edge.source || edge.from || edge.src || edge[0];
                target = edge.target || edge.to || edge.dst || edge[1];
            }
            
            if (source && target) {
                elements.push({
                    data: { 
                        id: `edge-${idx}`, 
                        source: source, 
                        target: target 
                    }
                });
            }
        });
    }

    // Initialize Cytoscape
    const hasSavedPositions = Object.keys(positionsMap).length > 0;
    
    const cy = cytoscape({
        container: container,
        elements: elements,
        style: [
            {
                selector: 'node',
                style: {
                    'width': 80,
                    'height': 80,
                    'background-color': 'transparent',
                    'background-opacity': 0,
                    'border-width': 0,
                    'border-color': 'transparent',
                    'background-fit': 'contain',
                    'background-repeat': 'no-repeat',
                    'background-clip': 'none',
                    'background-image-opacity': 1,
                    'background-blend-mode': 'multiply',
                    'bounds-expansion': 10,
                    'shape': 'rectangle',
                    // Use data mapper to get background-image from imageUrl data field
                    'background-image': 'data(imageUrl)',
                    // Label styling
                    'label': 'data(label)',
                    'text-valign': 'bottom',
                    'text-halign': 'center',
                    'text-margin-y': 8,
                    'font-size': '14px',
                    'font-weight': 'bold',
                    'color': '#000',
                    'text-outline-color': '#fff',
                    'text-outline-width': 2
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': '#666',
                    'target-arrow-color': '#666',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1.2,
                    'curve-style': 'taxi',
                    'taxi-direction': 'auto',
                    'taxi-turn': '50%',
                    'taxi-turn-min-distance': 30
                }
            }
        ],
        layout: hasSavedPositions ? 
            { name: 'preset' } :  // Use preset layout (no repositioning) if we have saved positions
            {
                name: 'dagre',  // Directed Acyclic Graph layout - great for flow diagrams
                rankDir: 'LR',  // Left-to-Right (use 'TB' for top-to-bottom)
                padding: 50,
                nodeSep: 80,    // Horizontal separation between nodes
                rankSep: 120,   // Vertical separation between ranks
                edgeSep: 20,    // Separation between edges
                ranker: 'network-simplex',  // Tightest layout
                animate: true,
                animationDuration: 500
            },
        wheelSensitivity: 0.2,
        minZoom: 0.3,
        maxZoom: 3
    });

    // Apply SVG data URIs to nodes after initialization
    if (nodes && nodes.length > 0) {
        for (const nodeId of nodes) {
            const node = cy.getElementById(nodeId);
            if (node && node.length > 0) {
                const svgUrl = node.data('svgUrl');
                if (svgUrl) {
                    try {
                        // Fetch and encode the SVG as a proper data URI
                        const response = await fetch(svgUrl);
                        if (response.ok) {
                            const svgText = await response.text();
                            // Use encodeURIComponent as per Cytoscape documentation for SVG data URIs
                            const dataUri = 'data:image/svg+xml;utf8,' + encodeURIComponent(svgText);
                            // Store the data URI in node data so the stylesheet mapper can use it
                            node.data('svgDataUri', dataUri);
                        } else {
                            console.warn('Failed to fetch SVG:', svgUrl);
                        }
                    } catch (err) {
                        console.error('Error loading SVG for node', nodeId, ':', err);
                    }
                }
            }
        }
    }

    // Snap-to-grid to ease horizontal/vertical alignment
    const GRID_SIZE = 40; // adjust to 5/10/20px as preferred
    function snapNodeToGrid(node) {
        const pos = node.position();
        const snapped = {
            x: Math.round(pos.x / GRID_SIZE) * GRID_SIZE,
            y: Math.round(pos.y / GRID_SIZE) * GRID_SIZE
        };
        node.position(snapped);
    }

    cy.on('dragfree', 'node', (evt) => {
        snapNodeToGrid(evt.target);
        saveNodePositions(cy);
    });
    
    // Also save positions when layout changes
    cy.on('layoutstop', () => {
        saveNodePositions(cy);
    });

    // Add interaction
    cy.on('tap', 'node', function(evt) {
        const node = evt.target;
        if (typeof window !== 'undefined' && typeof window.onGraphNodeClick === 'function') {
            try { 
                window.onGraphNodeClick(node.id()); 
            } catch (e) { 
                console.warn('onGraphNodeClick handler error', e); 
            }
        }
    });

    // Clicking on the background can be used to close the inspector
    cy.on('tap', function(evt) {
        if (evt.target === cy) {
            if (typeof window !== 'undefined' && typeof window.onGraphBlankClick === 'function') {
                try { window.onGraphBlankClick(); } catch (e) { /* no-op */ }
            }
        }
    });

    // Fit viewport to content
    cy.fit(50);
    
    return cy;
}
