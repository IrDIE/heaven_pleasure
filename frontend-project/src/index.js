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
  if (path.endsWith("index.html") && isAuthorized()) {
    window.location.href = "main_page.html";
    return;
  }

  if (path.endsWith("main_page.html") && !isAuthorized()) {
    // Not logged in → kick back to login
    window.location.href = "index.html";
    return;
  }

  // --- Login form handling (on index.html) ---
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", (e) => {
      e.preventDefault();

      // (Optional) You could validate inputs here
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value.trim();

      if (username && password) {
        authorizeUser();
        window.location.href = "main_page.html";
        return;
      } else {
        alert("Please enter username and password");
      }
    });
  }

  // --- Logout handling (on main_page.html) ---
  const logoutBtn = document.getElementById("logoutBtn");
  if (path.endsWith("main_page.html") && logoutBtn) {
    logoutBtn.addEventListener("click", (e) => {
      e.preventDefault();
      logoutUser();
      window.location.href = "index.html"; // go back to login page
      return;
    });
  }

  // --- Sign up link handling (on index.html) ---
  const signupLink = document.getElementById("signup-link");
  if (path.endsWith("index.html") && signupLink) {
    signupLink.addEventListener("click", (e) => {
      e.preventDefault(); // Prevent default anchor behavior
      signupLink.href = "create-account.html"; // Set the href attribute
      
      window.location.href = "create-account.html"; // Redirect to create-account.html
      return;
    });
  }

  const signupLinkFromCreate = document.getElementById("login-link");
  if (path.endsWith("create-account.html") && signupLinkFromCreate) {
    signupLinkFromCreate.addEventListener("click", (e) => {
      e.preventDefault(); // Prevent default anchor behavior
      signupLinkFromCreate.href = "index.html"; // Set the href attribute
      
      window.location.href = "index.html"; // Redirect to create-account.html
      return;
    });
  }

  const signupBtn = document.getElementById("signup-btn");
  if (signupBtn) {
    signupBtn.addEventListener("click", (e) => {
      e.preventDefault();
      authorizeUser();
      window.location.href = "main_page.html"; // Redirect to main_page.html
      return;
    });
  }

});

