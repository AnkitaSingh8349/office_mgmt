document.addEventListener("DOMContentLoaded", () => {
  loadEmployees();
});

const employeeList = document.getElementById("employeeList");
const employeeDetail = document.getElementById("employeeDetail");

/* ---------------- LOAD ALL EMPLOYEES ---------------- */
async function loadEmployees() {
  try {
    const res = await fetch("/admin/employees/all");
    if (!res.ok) throw new Error("Failed to load employees");

    const employees = await res.json();
    employeeList.innerHTML = "";

    if (employees.length === 0) {
      employeeList.innerHTML =
        `<li class="list-group-item text-muted">No employees found</li>`;
      return;
    }

    employees.forEach(emp => {
      const li = document.createElement("li");
      li.className = "list-group-item list-group-item-action";
      li.style.cursor = "pointer";
      li.innerHTML = `
        <div class="fw-semibold">${emp.name}</div>
        <small class="text-muted">${emp.email}</small>
      `;

      li.onclick = () => loadEmployeeDetail(emp.id);
      employeeList.appendChild(li);
    });

  } catch (err) {
    employeeList.innerHTML =
      `<li class="list-group-item text-danger">Error loading employees</li>`;
    console.error(err);
  }
}

/* ---------------- LOAD SINGLE EMPLOYEE DETAIL ---------------- */
async function loadEmployeeDetail(employeeId) {
  employeeDetail.innerHTML = `<div class="text-muted">Loading details…</div>`;

  try {
    const res = await fetch(`/admin/employees/${employeeId}`);
    if (!res.ok) throw new Error("Failed to load employee detail");

    const emp = await res.json();

    employeeDetail.innerHTML = `
      <h5 class="mb-3">${emp.name}</h5>

      <table class="table table-sm table-bordered">
        <tbody>
          <tr><th>Email</th><td>${emp.email || "-"}</td></tr>
          <tr><th>Phone</th><td>${emp.phone || "-"}</td></tr>
          <tr><th>Role</th><td>${emp.role || "-"}</td></tr>
          <tr><th>Status</th><td>${emp.status || "-"}</td></tr>
          <tr><th>Department ID</th><td>${emp.department_id || "-"}</td></tr>
          <tr><th>Salary</th><td>${emp.salary || "-"}</td></tr>
          <tr><th>Joining Date</th><td>${emp.joining_date || "-"}</td></tr>

          <tr class="table-secondary"><th colspan="2">Personal</th></tr>
          <tr><th>Birthday</th><td>${emp.birthday || "-"}</td></tr>
          <tr><th>Gender</th><td>${emp.gender || "-"}</td></tr>
          <tr><th>Marital Status</th><td>${emp.marital_status || "-"}</td></tr>
          <tr><th>Father Name</th><td>${emp.father_name || "-"}</td></tr>

          <tr class="table-secondary"><th colspan="2">Contact</th></tr>
          <tr><th>Personal Email</th><td>${emp.personal_email || "-"}</td></tr>
          <tr><th>Personal Mobile</th><td>${emp.personal_mobile || "-"}</td></tr>
          <tr><th>Seating Location</th><td>${emp.seating_location || "-"}</td></tr>

          <tr class="table-secondary"><th colspan="2">Identity</th></tr>
          <tr><th>UAN</th><td>${emp.uan || "-"}</td></tr>
          <tr><th>PAN</th><td>${emp.pan || "-"}</td></tr>
          <tr><th>Aadhar</th><td>${emp.aadhar || "-"}</td></tr>

          <tr class="table-secondary"><th colspan="2">Bank</th></tr>
          <tr><th>Bank Name</th><td>${emp.bank_name || "-"}</td></tr>
          <tr><th>Account No</th><td>${emp.bank_account_no || "-"}</td></tr>
          <tr><th>IFSC</th><td>${emp.ifsc_code || "-"}</td></tr>
          <tr><th>Account Type</th><td>${emp.account_type || "-"}</td></tr>
          <tr><th>Payment Mode</th><td>${emp.payment_mode || "-"}</td></tr>
        </tbody>
      </table>
    `;

  } catch (err) {
    employeeDetail.innerHTML =
      `<div class="text-danger">Error loading employee details</div>`;
    console.error(err);
  }
}
