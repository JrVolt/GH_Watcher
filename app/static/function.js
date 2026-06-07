
let charts={};

function format(d){return d.toISOString().split('T')[0];}

function setRange(start, end) {
    document.getElementById("start").value = format(start);
    document.getElementById("end").value = format(end);
    loadData();
}

function preset(days){
    let end=new Date();
    let start=new Date();
    start.setDate(end.getDate() - (days - 1));
    setRange(start, end);
}

function presetMonth(){
    let now=new Date();
    let start=new Date(now.getFullYear(),now.getMonth(),1);
    setRange(start, now);
}

function presetYear(){
    let now=new Date();
    let start=new Date(now.getFullYear(),0,1);
    setRange(start, now);
}

function presetAll(){
    const firstDate = document.getElementById("repo-first-date").value;
    const now = new Date();
    document.getElementById("start").value = firstDate || "2000-01-01";
    document.getElementById("end").value = format(now);
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
    const encodedRepo = encodeURIComponent(repo);
    const res=await fetch(`/data?repo=${encodedRepo}&start=${start}&end=${end}`);
    const data=await res.json();
    const labels=data.map(d=>d.date);
    const style = getComputedStyle(document.documentElement);

    const summaryRes = await fetch(`/summary?repo=${encodedRepo}&start=${start}&end=${end}`);
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

function setTableMessage(tbody, message){
    tbody.innerHTML = `<tr><td colspan="2" style="text-align:center; color:#8b98a6;">${message}</td></tr>`;
}

async function requestJson(url){
    const res = await fetch(url);
    const text = await res.text();
    let data;

    if (text) {
        try {
            data = JSON.parse(text);
        } catch (error) {
            throw new Error(`HTTP ${res.status}: ${text.trim().slice(0, 200)}`);
        }
    }

    if (!res.ok) {
        const message = data?.detail || data?.message || data?.error || `${res.status} ${res.statusText}`;
        throw new Error(`HTTP ${res.status}: ${message}`);
    }
    if (data?.error || data?.message || data?.detail) {
        throw new Error(data.detail || data.message || data.error);
    }
    return data;
}

async function loadReferrers(repo){
    const start=document.getElementById("start").value;
    const end=document.getElementById("end").value;
    const encodedRepo = encodeURIComponent(repo);
    const tbody=document.getElementById("referrers");
    try {
        const data = await requestJson(`/referrers?repo=${encodedRepo}&start=${start}&end=${end}`);
        if(!Array.isArray(data) || data.length===0){
            setTableMessage(tbody, "No referrer data available");
            return;
        }
        tbody.innerHTML = "";
        data.forEach(r=>{
            tbody.innerHTML+=`<tr><td>${r.referrer}</td><td>${r.count}</td></tr>`;
        });
    } catch (error) {
        console.error(error);
        setTableMessage(tbody, error.message || "Unable to load referrer data");
    }
}

async function loadPaths(repo){
    const start=document.getElementById("start").value;
    const end=document.getElementById("end").value;
    const encodedRepo = encodeURIComponent(repo);
    const tbody=document.getElementById("paths");
    try {
        const data = await requestJson(`/popular-paths?repo=${encodedRepo}&start=${start}&end=${end}`);
        if(!Array.isArray(data) || data.length===0){
            setTableMessage(tbody, "No popular path data available");
            return;
        }
        tbody.innerHTML = "";
        data.forEach(p=>{
            tbody.innerHTML+=`<tr><td>${p.path}</td><td>${p.count}</td></tr>`;
        });
    } catch (error) {
        console.error(error);
        setTableMessage(tbody, error.message || "Unable to load path data");
    }
}

window.onload=()=>{
    const selectedRepo = getQueryParam('repo');
    const repoSelect = document.getElementById('repo');
    if (repoSelect && selectedRepo) {
        repoSelect.value = selectedRepo;
    }

    const firstDate = document.getElementById("repo-first-date").value;
    const end = new Date();
    document.getElementById("end").value = format(end);
    if (firstDate) {
        document.getElementById("start").value = firstDate;
    } else {
        presetYear();
        return;
    }
    loadData();
}

