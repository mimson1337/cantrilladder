// Ladder behavior extracted from template: handles vertical ladder UI
document.addEventListener('DOMContentLoaded', function(){
  const steps = Array.from(document.querySelectorAll('.ladder-step'));
  if(!steps.length) return;
  const out = document.getElementById('out');
  const hidden = document.getElementById('answer_input');
  const defaultVal = 5;

  function setValue(v){
    if(out) out.textContent = v;
    if(hidden) hidden.value = v;
    steps.forEach(s => {
      const val = Number(s.dataset.value);
      if(val <= v){
        s.setAttribute('aria-checked','true');
        s.classList.add('active');
        s.style.background = '';
      } else {
        s.setAttribute('aria-checked','false');
        s.classList.remove('active');
      }
    });
  }

  steps.forEach(s => {
    s.addEventListener('click', () => setValue(Number(s.dataset.value)));
    s.addEventListener('keydown', (e) => {
      const cur = Number(hidden.value || defaultVal);
      if(e.key === 'ArrowDown'){
        e.preventDefault(); setValue(Math.max(1, cur - 1));
      } else if(e.key === 'ArrowUp'){
        e.preventDefault(); setValue(Math.min(10, cur + 1));
      } else if(e.key === 'Enter' || e.key === ' '){
        e.preventDefault(); setValue(Number(s.dataset.value));
      }
    });
    s.tabIndex = 0;
  });

  setValue(defaultVal);
});
