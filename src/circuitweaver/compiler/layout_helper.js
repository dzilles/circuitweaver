const ELK = require('elkjs');
const elk = new ELK();

let inputData = '';
process.stdin.on('data', chunk => { inputData += chunk; });

process.stdin.on('end', async () => {
    try {
        if (!inputData) {
            process.exit(0);
        }
        const graph = JSON.parse(inputData);
        
        // Note: ALL layoutOptions are now provided by the Python payload
        const layout = await elk.layout(graph);
        process.stdout.write(JSON.stringify(layout)); 
    } catch (err) {
        console.error('Error during layout:', err);
        process.exit(1);
    }
});
