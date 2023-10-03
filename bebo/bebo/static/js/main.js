
/*
 * Copyright (c) 2019-2023 SRI International.
 */

// from: https://stackoverflow.com/a/12845144/3816489
var interval = null;

function setRefreshInterval() {
  if (interval != null)
    clearInterval(interval)

  var seconds = $("#refreshInterval :selected").val();
  console.log("New Interval: " + seconds +"s");
  if (seconds > 0) {
    interval = setInterval("location.reload(true);", seconds * 1000)
  } else {
    interval = null
  }
}
