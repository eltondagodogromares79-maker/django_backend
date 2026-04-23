(function () {
  function byId(id) {
    return document.getElementById(id);
  }

  function clearOptions(select) {
    while (select.options.length > 0) {
      select.remove(0);
    }
  }

  function addOption(select, value, text) {
    var option = document.createElement('option');
    option.value = value;
    option.text = text;
    select.add(option);
  }

  function setLoading(select, isLoading) {
    if (isLoading) {
      select.disabled = true;
      select.dataset.loading = '1';
    } else {
      select.disabled = false;
      delete select.dataset.loading;
    }
  }

  function updatePrograms(departmentSelect, programSelect) {
    var url =
      departmentSelect.getAttribute('data-programs-url') ||
      programSelect.getAttribute('data-programs-url');
    var departmentId = departmentSelect.value;

    console.log('[AdviserForm] departmentSelect:', departmentSelect);
    console.log('[AdviserForm] programSelect:', programSelect);
    console.log('[AdviserForm] programs URL:', url);
    console.log('[AdviserForm] departmentId:', departmentId);

    if (!departmentId || !url) {
      clearOptions(programSelect);
      addOption(programSelect, '', '---------');
      console.warn('[AdviserForm] Missing department or URL; cleared program options.');
      return;
    }

    clearOptions(programSelect);
    addOption(programSelect, '', '---------');

    setLoading(programSelect, true);

    fetch(url + '?department_id=' + encodeURIComponent(departmentId), {
      credentials: 'same-origin'
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        console.log('[AdviserForm] programs response:', data);
        if (data && data.results) {
          data.results.forEach(function (item) {
            addOption(programSelect, item.id, item.name);
          });
        }
      })
      .catch(function () {
        // keep dropdown with only placeholder on error
        console.error('[AdviserForm] Failed to fetch programs.');
      })
      .finally(function () {
        setLoading(programSelect, false);
      });
  }

  function findSelectByNameSuffix(suffix) {
    var els = document.querySelectorAll('select[name$="' + suffix + '"]');
    return els.length ? els[0] : null;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var departmentSelect = byId('id_department') || findSelectByNameSuffix('department');
    var programSelect = byId('id_program') || findSelectByNameSuffix('program');
    if (!departmentSelect || !programSelect) {
      console.warn('[AdviserForm] Could not find department or program select.');
      return;
    }

    function onDepartmentChange() {
      updatePrograms(departmentSelect, programSelect);
    }

    departmentSelect.addEventListener('change', onDepartmentChange);
    departmentSelect.addEventListener('input', onDepartmentChange);

    if (window.jQuery) {
      window.jQuery(departmentSelect).on('select2:select', onDepartmentChange);
      window.jQuery(departmentSelect).on('change', onDepartmentChange);
    }

    if (departmentSelect.value) {
      updatePrograms(departmentSelect, programSelect);
    }
  });
})();
