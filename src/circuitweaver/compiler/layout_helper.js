const ELK = require('elkjs');
const fs = require('fs');

if (process.argv.length < 3) {
    console.error('Usage: node layout_helper.js <input_elk_json> [output_layout_json]');
    process.exit(1);
}

const inputFile = process.argv[2];
const outputFile = process.argv[3];

const elk = new ELK();

async function run() {
    try {
        const graph = JSON.parse(fs.readFileSync(inputFile, 'utf8'));

        // Default layout options
        const layoutOptions = {
            'elk.algorithm': 'layered',
            'elk.direction': 'RIGHT',
            'elk.edgeRouting': 'ORTHOGONAL',
            'elk.layered.spacing.nodeNodeBetweenLayers': '60',
            'elk.spacing.nodeNode': '40',
            'org.eclipse.elk.portConstraints': 'FIXED_POS'
        };

        graph.layoutOptions = Object.assign({}, layoutOptions, graph.layoutOptions || {});

        const layout = await elk.layout(graph);
        
        if (outputFile) {
            fs.writeFileSync(outputFile, JSON.stringify(layout, null, 2));
        } else {
            console.log(JSON.stringify(layout, null, 2));
        }
    } catch (err) {
        console.error('Error during layout:', err);
        process.exit(1);
    }
}

run();
