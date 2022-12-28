function ready(fn) {
  if (document.readyState !== 'loading') {
    fn();
  } else {
    document.addEventListener('DOMContentLoaded', fn);
  }
}

ready(() => {
  const loginForm = document.getElementById('loginform');
  const userSelect = document.getElementById('users');
  const uid = localStorage.getItem('uid');

  loginForm.onsubmit = function() {
      localStorage.setItem('uid', userSelect.value);
  };

  if (uid !== null) {
    userSelect.value = uid;
  }
});
