var dagfuncs = window.dashAgGridFunctions = window.dashAgGridFunctions || {};

dagfuncs.valueGradient = function(params) {
    if (params.node.rowPinned) return {};
    var val = params.value;
    if (val === null || val === undefined || isNaN(val)) return {};

    var min = params.context.valueMin;
    var max = params.context.valueMax;
    var range = (max - min) !== 0 ? (max - min) : 1;

    var pct = (val - min) / range;
    pct = Math.max(0, Math.min(1, pct));

    return {
        backgroundColor: 'rgba(0, 123, 167, ' + pct + ')',
        color: '#fff'
    };
};