// --- AUTH STATE ---
function isAuthorized() {
  return localStorage.getItem("authorized") === "true";
}

function authorizeUser() {
  localStorage.setItem("authorized", "true");
}

function logoutUser() {
  localStorage.removeItem("authorized");

}

// --- PAGE LOGIC ---
document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;

  // --- Redirects ---
  if (path.endsWith("index") && isAuthorized()) {
    window.location.href = "main_page";
    return;
  }

  if (path.endsWith("main_page") && !isAuthorized()) {
    // Not logged in → kick back to login
    window.location.href = "index";
    return;
  }

  // --- Login form handling (on index.html) ---
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      // (Optional) You could validate inputs here
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value.trim();
      try {
        const response = await fetch('http://localhost:5000/api/login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (data.success) {
          if (username && password) {
            // Store user data in localStorage
            localStorage.setItem('user', JSON.stringify(data.user));
            // Redirect to main page
            authorizeUser();
            window.location.href = "main_page"; // Redirect to main_page.html
            return;

          } else {
            alert("Please enter username and password");
          }

        } else {
          alert('Login failed: ' + data.message);
        }

      } catch (error) {
        console.error('Error:', error);
        alert('An error occurred during login');
      } finally {
        loginBtn.textContent = 'Log in';
        loginBtn.disabled = false;
      }
    });
  }

  // --- Logout handling (on main_page.html) ---
  const logoutBtn = document.getElementById("logoutBtn");
  if (path.endsWith("main_page") && logoutBtn) {
    logoutBtn.addEventListener("click", (e) => {
      e.preventDefault();
      logoutUser();
      window.location.href = "index"; // go back to login page
      return;
    });
  }

  // --- Sign up link handling (on index.html) ---
  const signupLink = document.getElementById("signup-link");
  if (path.endsWith("index") && signupLink) {
    signupLink.addEventListener("click", (e) => {
      e.preventDefault(); // Prevent default anchor behavior
      signupLink.href = "create-account"; // Set the href attribute

      window.location.href = "create-account"; // Redirect to create-account.html
      return;
    });
  }

  const signupLinkFromCreate = document.getElementById("login-link");
  if (path.endsWith("create-account") && signupLinkFromCreate) {
    signupLinkFromCreate.addEventListener("click", (e) => {
      e.preventDefault(); // Prevent default anchor behavior
      signupLinkFromCreate.href = "index"; // Set the href attribute

      window.location.href = "index"; // Redirect to create-account.html
      return;
    });
  }
  //// create new user
  const signupBtn = document.getElementById("signup-btn");
  if (signupBtn) {
    signupBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value.trim();
      try {
        const response = await fetch('http://localhost:5000/api/create-account', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (data.success) {
          if (username && password) {
            // Store user data in localStorage
            localStorage.setItem('user', JSON.stringify(data.user));
            // Redirect to main page
            authorizeUser();
            window.location.href = "main_page"; // Redirect to main_page.html
            return;

          } else {
            alert("Please enter username and password");
          }

        } else {
          alert('Login failed: You need to create account first' + data.message);
        }

      } catch (error) {
        console.error('Error:', error);
        alert('An error occurred during login');
      } finally {
        loginBtn.textContent = 'Log in';
        loginBtn.disabled = false;
      }

      // authorizeUser();
      // window.location.href = "main_page"; // Redirect to main_page.html
      // return;
    });
  }

});

