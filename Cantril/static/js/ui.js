document.addEventListener('DOMContentLoaded', function(){
  var toggle = document.getElementById('nav_toggle');
  var nav = document.getElementById('main_nav');
  if(!toggle || !nav) return;

  toggle.addEventListener('click', function(){
    var expanded = this.getAttribute('aria-expanded') === 'true';
    this.setAttribute('aria-expanded', (!expanded).toString());
    nav.classList.toggle('open');
  });

  // Close nav on resize above mobile breakpoint
  var mq = window.matchMedia('(min-width:481px)');
  function handleResize(e){
    if(e.matches){
      nav.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    }
  }
  mq.addListener(handleResize);
  handleResize(mq);
});
