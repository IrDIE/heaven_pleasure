(function(){
  const treeData = JSON.parse(document.getElementById('__TREE__').textContent);
  const issuesByFile = JSON.parse(document.getElementById('__ISSUES__').textContent);

  const elTree = document.getElementById('tree');
  const elContent = document.getElementById('content');
  const elSearch = document.getElementById('search');

  function cnts(c){
    const get = (k) => (c && c[k]) || 0;
    const mk = (v, cls) => v ? `<span class="c ${cls}">${v}</span>` : '';
    return [
      mk(get('critical'),'cr'),
      mk(get('major'),'ma'),
      mk(get('minor'),'mi'),
      mk(get('info'),'in'),
    ].join('');
  }

  function row(name, isFile, counts){
    const toggle = isFile
      ? '<span class="toggle" aria-hidden="true">·</span>'
      : '<span class="toggle" aria-hidden="true">+</span>';
    return `
      <div class="row" data-file="${isFile}">
        ${toggle}
        <span class="name" title="${name}">${name}</span>
        <span class="cnts">${cnts(counts)}</span>
      </div>`;
  }

  function renderNodes(nodes){
    return nodes.map(n=>{
      const hasKids = !n.is_file && n.children && n.children.length;
      const kidsHtml = hasKids ? `<ul class="tree hidden">${renderNodes(n.children)}</ul>` : '';
      return `<li>${row(n.name, n.is_file, n.counts)}${kidsHtml}</li>`;
    }).join('');
  }

  elTree.innerHTML = `<ul class="tree">${renderNodes(treeData.children||[])}</ul>`;

  elTree.addEventListener('click', (e)=>{
    const row = e.target.closest('.row');
    if(!row) return;

    const li = row.parentElement;
    const trail = [];
    let cur = li;
    while(cur && cur !== elTree){
      const r = cur.querySelector(':scope > .row .name');
      if(r) trail.unshift(r.textContent);
      cur = cur.parentElement.closest('li');
    }
    const path = trail.join('/');

    if(row.dataset.file === 'true'){
      renderFile(path);
    } else {
      const sub = li.querySelector(':scope > ul.tree');
      if(sub){
        sub.classList.toggle('hidden');
        const tgl = row.querySelector('.toggle');
        if(tgl) tgl.textContent = sub.classList.contains('hidden') ? '+' : '–';
      }
    }
  });

  function esc(s){
    const div = document.createElement('div');
    div.textContent = s == null ? '' : String(s);
    return div.innerHTML;
  }

  function renderSnippet(issue){
    const code = issue.snippet || [];
    const hi = issue.highlight;
    const rng = (issue.snippet_range||{});
    const start = rng.start || 1;

    if(!code.length){
      return '<p class="empty">Фрагмент недоступен.</p>';
    }

    const lines = code.map((ln, i)=>{
      const lnNo = start + i;
      const cls = (typeof hi==='number' && i===hi) ? 'code-line hl' : 'code-line';
      const safe = esc(ln).replace(/ /g, '&nbsp;'); // сохраняем пробелы
      
      return `<div class="${cls}">
        <span class="ln">${lnNo}</span>
        <span class="lc">${safe}</span>
      </div>`;
    }).join('');

    return `<pre class="code"><code>${lines}</code></pre>`;
  }

  function renderFile(relPath){
    const issues = issuesByFile[relPath] || [];
    if(!issues.length){
      elContent.innerHTML = `
        <h2>📄 ${esc(relPath)}</h2>
        <p class="empty">Ошибок не найдено.</p>`;
      return;
    }

    const blocks = issues.map(it=>{
      const sev = (it._sev||'minor');
      const fileTag = it.file_resolved || it.file || it.path || relPath;
      const badges = `
        <span class="badge b-${sev==='critical'?'crit':sev}">${sev}</span>
        <span class="badge">${esc(fileTag)}${it.line?':'+it.line:''}</span>`;
      return `
        <div class="issue">
          <h3>${esc(it.id||'')}${it._title?' · '+esc(it._title):''}</h3>
          <div class="meta">${badges}</div>
          ${it._desc?`<p>${esc(it._desc)}</p>`:''}
          ${renderSnippet(it)}
        </div>`;
    }).join('');

    elContent.innerHTML = `<h2>📄 ${esc(relPath)}</h2>${blocks}`;

    const firstHL = elContent.querySelector('.code-line.hl');
    if(firstHL) firstHL.scrollIntoView({behavior:'smooth', block:'center'});
  }

  // Поиск по именам узлов (файлы/папки)
  const search = document.getElementById('search');
  if(search){
    search.addEventListener('input', ()=>{
      const q = search.value.trim().toLowerCase();
      const items = elTree.querySelectorAll('li');
      items.forEach(li=>{
        const nameEl = li.querySelector(':scope > .row .name');
        if(!nameEl) return;
        const ok = !q || nameEl.textContent.toLowerCase().includes(q);
        li.style.display = ok ? '' : 'none';
      });
    });
  }
})();
