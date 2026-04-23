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

  function updateSubjects(programSelect, yearLevelSelect, termSelect, subjectsField) {
    var url = subjectsField.getAttribute('data-subjects-url');
    var programId = programSelect ? programSelect.value : '';
    var yearLevelId = yearLevelSelect ? yearLevelSelect.value : '';
    var termId = termSelect ? termSelect.value : '';

    subjectsField.value = '';

    if (!url || !yearLevelId || !termId) {
      return;
    }

    subjectsField.value = 'Loading subjects...';
    setLoading(subjectsField, true);

    var params = new URLSearchParams();
    if (programId) {
      params.append('program_id', programId);
    }
    params.append('year_level_id', yearLevelId);
    params.append('term_id', termId);

    fetch(url + '?' + params.toString(), {
      credentials: 'same-origin'
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        var lines = [];
        if (data && data.results && data.results.length) {
          data.results.forEach(function (item) {
            lines.push(item.code + ' - ' + item.name);
          });
        }

        if (!lines.length) {
          if (data && data.notice) {
            lines.push(data.notice);
          } else {
            lines.push('No subjects found for this selection.');
          }
        }

        subjectsField.value = lines.join('\n');
      })
      .catch(function () {
        subjectsField.value = 'Unable to load subjects.';
      })
      .finally(function () {
        setLoading(subjectsField, false);
      });
  }

  function updateYearLevels(programSelect, yearLevelSelect) {
    var url = programSelect.getAttribute('data-year-levels-url');
    var programId = programSelect.value;

    clearOptions(yearLevelSelect);
    addOption(yearLevelSelect, '', '---------');

    if (!programId || !url) {
      return;
    }

    setLoading(yearLevelSelect, true);

    fetch(url + '?program_id=' + encodeURIComponent(programId), {
      credentials: 'same-origin'
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (data && data.results) {
          data.results.forEach(function (item) {
            addOption(yearLevelSelect, item.id, item.name);
          });
        }
      })
      .catch(function () {
        // keep dropdown with only placeholder on error
      })
      .finally(function () {
        setLoading(yearLevelSelect, false);
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var programSelect = byId('id_program');
    var yearLevelSelect = byId('id_year_level');
    var termSelect = byId('id_term');
    var subjectsField = byId('id_available_subjects');
    if (!programSelect || !yearLevelSelect) {
      return;
    }

    programSelect.addEventListener('change', function () {
      updateYearLevels(programSelect, yearLevelSelect);
      if (subjectsField) {
        subjectsField.value = '';
      }
    });

    if (yearLevelSelect && termSelect && subjectsField) {
      yearLevelSelect.addEventListener('change', function () {
        updateSubjects(programSelect, yearLevelSelect, termSelect, subjectsField);
      });
      termSelect.addEventListener('change', function () {
        updateSubjects(programSelect, yearLevelSelect, termSelect, subjectsField);
      });
      updateSubjects(programSelect, yearLevelSelect, termSelect, subjectsField);
    }
  });
})();
