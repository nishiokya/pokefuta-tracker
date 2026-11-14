// Credits are read from the published rows at runtime, never stored in Git.
// One bounded query for only the photos rendered on this page; no 200-row list limit.
const toggle = document.getElementById('cw-photo-mode');
if (toggle) {
  toggle.hidden = false;
  toggle.addEventListener('click', () => {
    const original = document.body.classList.toggle('cw-photos-original');
    toggle.setAttribute('aria-pressed', String(!original));
    toggle.textContent = original ? 'ふただけ表示：オフ' : 'ふただけ表示：オン';
  });
}

const credits = [...document.querySelectorAll('[data-photo-author]')];
const ids = [...new Set(credits.map(node => node.dataset.photoAuthor))]
  .filter(id => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id));
if (ids.length) {
  try {
    const { supabase } = await import('./pokefuta-auth.js');
    const names = new Map();
    for (let i = 0; i < ids.length; i += 50) {
      const { data, error } = await supabase.from('design_manhole')
        .select('id,submitter_name').eq('status', 'published').in('id', ids.slice(i, i + 50));
      if (error) throw error;
      for (const row of data || []) {
        const name = typeof row.submitter_name === 'string' ? row.submitter_name.trim() : '';
        if (name) names.set(row.id, name);
      }
    }
    for (const node of credits) {
      const name = names.get(node.dataset.photoAuthor);
      if (name) node.textContent = `撮影：${name}`;
    }
  } catch {
    // Photos and post links remain usable when the public credit lookup is unavailable.
  }
}
