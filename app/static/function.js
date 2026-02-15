
function toggleTheme(){
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.querySelector('button[onclick="toggleTheme()"]').textContent = next === 'dark' ? '🌙' : '☀️';
}

let charts={};

function format(d){return d.toISOString().split('T')[0];}

function preset(days){
    let end=new Date();
    let start=new Date();
    start.setDate(end.getDate()-days);
    document.getElementById("start").value=format(start);
    document.getElementById("end").value=format(end);
    loadData();
}

function presetMonth(){
    let now=new Date();
    let start=new Date(now.getFullYear(),now.getMonth(),1);
    document.getElementById("start").value=format(start);
    document.getElementById("end").value=format(now);
    loadData();
}

function presetYear(){
    let now=new Date();
    let start=new Date(now.getFullYear(),0,1);
    document.getElementById("start").value=format(start);
    document.getElementById("end").value=format(now);
    loadData();
}

function getColors() {
    const style = getComputedStyle(document.documentElement);
    return {
        clones: style.getPropertyValue('--color-clones').trim(),
        uniqueClones: style.getPropertyValue('--color-unique-clones').trim(),
        views: style.getPropertyValue('--color-views').trim(),
        uniqueViews: style.getPropertyValue('--color-unique-views').trim()
    };
}

async function loadData(){
    const repo=document.getElementById("repo").value;
    const start=document.getElementById("start").value;
    const end=document.getElementById("end").value;
    const res=await fetch(`/data?repo=${repo}&start=${start}&end=${end}`);
    const data=await res.json();
    const labels=data.map(d=>d.date);
    const style = getComputedStyle(document.documentElement);

    makeChart("clonesChart","Clones",labels,[
        {label:"Clones", data:data.map(d=>d.clones), borderColor:style.getPropertyValue('--color-clones').trim(), fill:false, tension:0.1, borderDash:[]},
        {label:"Unique Clones", data:data.map(d=>d.unique_clones), borderColor:style.getPropertyValue('--color-unique-clones').trim(), fill:false, tension:0.1, borderDash:[5,5]}
    ]);

    makeChart("viewsChart","Views",labels,[
        {label:"Views", data:data.map(d=>d.views), borderColor:style.getPropertyValue('--color-views').trim(), fill:false, tension:0.1, borderDash:[]},
        {label:"Unique Views", data:data.map(d=>d.unique_views), borderColor:style.getPropertyValue('--color-unique-views').trim(), fill:false, tension:0.1, borderDash:[5,5]}
    ]);

    loadReferrers(repo);
    loadPaths(repo);
}

function makeChart(id,label,labels,datasets){
    if(charts[id]) charts[id].destroy();
    charts[id]=new Chart(document.getElementById(id),{
        type:"line",
        data:{labels:labels,datasets:datasets},
        options:{
            responsive:true, 
            maintainAspectRatio:true, 
            plugins:{legend:{display:true}},
            scales:{
                x:{ticks:{maxTicksLimit:10}},
                y:{beginAtZero:true, ticks:{stepSize:1, callback:val=>Number.isInteger(val)?val:''}}
            }
        }
    });
}

async function loadReferrers(repo){
    const res=await fetch(`/referrers?repo=${repo}`);
    const data=await res.json();
    let tbody=document.getElementById("referrers");
    tbody.innerHTML="";
    if(!data || data.length===0){tbody.innerHTML="<tr><td colspan=2>No data</td></tr>";return;}
    data.forEach(r=>{
        tbody.innerHTML+=`<tr><td>${r.referrer}</td><td>${r.count}</td></tr>`;
    });
}

async function loadPaths(repo){
    const res=await fetch(`/popular-paths?repo=${repo}`);
    const data=await res.json();
    let tbody=document.getElementById("paths");
    tbody.innerHTML="";
    if(!data || data.length===0){tbody.innerHTML="<tr><td colspan=2>No data</td></tr>";return;}
    data.forEach(p=>{
        tbody.innerHTML+=`<tr><td>${p.path}</td><td>${p.count}</td></tr>`;
    });
}

function exportPDF(){
    const element = document.querySelector('.container');
    const opt = {
        margin: 5,
        filename: 'github-traffic-report.pdf',
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2 },
        jsPDF: { orientation: 'landscape', unit: 'mm', format: 'a4' },
        pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
    };
    html2pdf().set(opt).from(element).save();
}

window.onload=()=>{preset(14); loadData();}

