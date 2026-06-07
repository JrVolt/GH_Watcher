
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

function getQueryParam(name){
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}

function onRepoChange(){
    const repo = document.getElementById("repo").value;
    if (window.location.pathname === '/repo') {
        const newUrl = `/repo?repo=${encodeURIComponent(repo)}`;
        window.history.replaceState(null, '', newUrl);
        loadData();
    } else {
        window.location.href = `/repo?repo=${encodeURIComponent(repo)}`;
    }
}

async function loadData(){
    const repo=document.getElementById("repo").value;
    const start=document.getElementById("start").value;
    const end=document.getElementById("end").value;
    const res=await fetch(`/data?repo=${repo}&start=${start}&end=${end}`);
    const data=await res.json();
    const labels=data.map(d=>d.date);
    const style = getComputedStyle(document.documentElement);

    const summaryRes = await fetch(`/summary?repo=${repo}&start=${start}&end=${end}`);
    const summary = await summaryRes.json();
    document.getElementById("total-downloads").textContent = summary.range.clones;
    document.getElementById("total-views").textContent = summary.range.views;
    document.getElementById("first-date").textContent = summary.first_date || "—";
    document.getElementById("tracked-days").textContent = summary.tracked_days;
    document.getElementById("best-day-count").textContent = summary.best_day.clones ?? 0;
    document.getElementById("best-day-date").textContent = summary.best_day.date || "—";

    makeChart("clonesChart","Clones",labels,[
        {label:"Clones", data:data.map(d=>d.clones), borderColor:style.getPropertyValue('--color-clones').trim(), fill:false, tension:0.1, borderDash:[25,15]},
        {label:"Unique Clones", data:data.map(d=>d.unique_clones), borderColor:style.getPropertyValue('--color-unique-clones').trim(), fill:false, tension:0.1, borderDash:[]}
    ]);

    makeChart("viewsChart","Views",labels,[
        {label:"Views", data:data.map(d=>d.views), borderColor:style.getPropertyValue('--color-views').trim(), fill:false, tension:0.1, borderDash:[25,15]},
        {label:"Unique Views", data:data.map(d=>d.unique_views), borderColor:style.getPropertyValue('--color-unique-views').trim(), fill:false, tension:0.1, borderDash:[]}
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
    const start=document.getElementById("start").value;
    const end=document.getElementById("end").value;
    const res=await fetch(`/referrers?repo=${repo}&start=${start}&end=${end}`);
    const data=await res.json();
    let tbody=document.getElementById("referrers");
    tbody.innerHTML="";
    if(!data || data.length===0){tbody.innerHTML="<tr><td colspan=2>No data</td></tr>";return;}
    data.forEach(r=>{
        tbody.innerHTML+=`<tr><td>${r.referrer}</td><td>${r.count}</td></tr>`;
    });
}

async function loadPaths(repo){
    const start=document.getElementById("start").value;
    const end=document.getElementById("end").value;
    const res=await fetch(`/popular-paths?repo=${repo}&start=${start}&end=${end}`);
    const data=await res.json();
    let tbody=document.getElementById("paths");
    tbody.innerHTML="";
    if(!data || data.length===0){tbody.innerHTML="<tr><td colspan=2>No data</td></tr>";return;}
    data.forEach(p=>{
        tbody.innerHTML+=`<tr><td>${p.path}</td><td>${p.count}</td></tr>`;
    });
}

window.onload=()=>{
    const selectedRepo = getQueryParam('repo');
    const repoSelect = document.getElementById('repo');
    if (repoSelect && selectedRepo) {
        repoSelect.value = selectedRepo;
    }
    preset(14);
    loadData();
}

