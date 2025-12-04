// app/static/auth.js
// Simple login + signup handler (works with /login and /signup)
// Login code left as you originally had it; signup code replaced to use FormData
// + small floating success pop-up on signup success.

document.addEventListener("DOMContentLoaded", function () {

  // ---------- LOGIN (unchanged logic) ----------
  const loginForm = document.getElementById("loginForm");
  const loginAlert = document.getElementById("loginAlert");

  if (loginForm) {
    loginForm.addEventListener("submit", async function (e) {
      e.preventDefault();

      const email = (loginForm.email && loginForm.email.value || "").trim();
      const password = (loginForm.password && loginForm.password.value || "").trim();

      if (!email || !password) {
        if (loginAlert) { loginAlert.innerText = "Email and password required"; loginAlert.classList.remove("d-none"); }
        else alert("Email and password required");
        return;
      }

      try {
        // <-- make sure this matches your backend route: /login
        const res = await fetch("/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
          },
          credentials: "same-origin",
          body: JSON.stringify({ email, password })
        });

        const data = await safeJson(res);

        if (!res.ok) {
          const msg = data && data.error ? data.error : "Login failed";
          if (loginAlert) { loginAlert.innerText = msg; loginAlert.classList.remove("d-none"); }
          else alert(msg);
          return;
        }

        // success -> server should return { "redirect": "/go_admin" } or similar
        if (data && data.redirect) {
          window.location.href = data.redirect;
        } else {
          // fallback: go to home
          window.location.href = "/";
        }

      } catch (err) {
        if (loginAlert) { loginAlert.innerText = "Network error"; loginAlert.classList.remove("d-none"); }
        else alert("Network error");
      }
    });
  }

  // ---------- SIGNUP (REPLACED) ----------
  // Uses FormData so FastAPI Form(...) params are populated.
  const signupForm = document.getElementById("signupForm");
  const signupAlert = document.getElementById("signupAlert");

  if (signupForm) {
    signupForm.addEventListener("submit", async function (e) {
      e.preventDefault();

      const name = (signupForm.name && signupForm.name.value || "").trim();
      const email = (signupForm.email && signupForm.email.value || "").trim();
      const password = (signupForm.password && signupForm.password.value || "").trim();

      if (!name || !email || !password) {
        showSignupError("All fields required");
        return;
      }
      if (password.length < 6) {
        showSignupError("Password must be at least 6 characters");
        return;
      }

      try {
        const form = new FormData();
        form.append("name", name);
        form.append("email", email);
        form.append("password", password);
        // optional fields: same code, only add pop box on success
        if (signupForm.phone) form.append("phone", signupForm.phone.value || "");
        form.append("role", signupForm.role ? signupForm.role.value : "employee");

        const res = await fetch("/signup", {
          method: "POST",
          body: form,
          credentials: "same-origin", // include cookies
          headers: {
            "X-Requested-With": "XMLHttpRequest" // tell server it's AJAX
          }
        });

        const data = await safeJson(res);

        if (!res.ok) {
          const msg = data && data.error ? data.error : "Signup failed";
          showSignupError(msg);
          return;
        }

        // success -> show floating pop-up (toast) then redirect
        const redirectTo = (data && data.redirect) ? data.redirect : "/go_employee";
        showSignupSuccessToast("Account created — redirecting...", 1500, redirectTo);

      } catch (err) {
        showSignupError("Network error");
      }
    });
  }

  function showSignupError(msg) {
    if (signupAlert) {
      signupAlert.innerText = msg;
      signupAlert.classList.remove("d-none");
      // ensure it's styled as an error if using bootstrap
      signupAlert.classList.remove("alert-success");
      signupAlert.classList.add("alert-danger");
    } else {
      alert(msg);
    }
  }

  // Create and show a small floating toast in the top-right of the page.
  function showSignupSuccessToast(message, ms = 1500, redirectUrl = "/go_employee") {
    // remove any existing toast
    const existing = document.getElementById("signup-success-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "signup-success-toast";
    toast.style.position = "fixed";
    toast.style.top = "16px";
    toast.style.right = "16px";
    toast.style.zIndex = 9999;
    toast.style.background = "#28a745";
    toast.style.color = "#fff";
    toast.style.padding = "12px 18px";
    toast.style.borderRadius = "8px";
    toast.style.boxShadow = "0 6px 18px rgba(0,0,0,0.12)";
    toast.style.fontWeight = "600";
    toast.style.opacity = "0";
    toast.style.transition = "opacity 180ms ease, transform 180ms ease";
    toast.style.transform = "translateY(-6px)";
    toast.innerText = message;

    document.body.appendChild(toast);

    // trigger show
    requestAnimationFrame(() => {
      toast.style.opacity = "1";
      toast.style.transform = "translateY(0)";
    });

    // hide after timeout, then redirect
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-6px)";
      setTimeout(() => {
        toast.remove();
        // redirect after toast disappears
        window.location.href = redirectUrl;
      }, 220);
    }, ms);
  }

  async function safeJson(response) {
    try { return await response.json(); } catch (e) { return null; }
  }

});
