/*
 * Copyright (c) 2019-2023 SRI International.
 */

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function make_backoff(initial, cap = 1000) {
  let backoff = initial;

  return async function() {
    await sleep(backoff);
    backoff *= 2;
  }
}

async function tenacious_fetch(url, options = {}) {
  const backoff = make_backoff(100);
  let response = null;
  while(true) {
    try {
      response = await fetch(url, options);
    } catch(e) {}

    if (response && response.ok) {
      return await response.json();
    }

    await backoff();
  }
}

export async function post_json(url, data) {
  return await tenacious_fetch(url, {
    method: "POST",
    headers: {"Content-type": "application/json"},
    body: JSON.stringify(data)
  });
}

export async function get_json(url, params = {}) {
  if (Object.keys(params).length) {
    url = url + "?" + Object.entries(params).map(([k, v]) => `${k}=${v}`).join("&")
  }
  return await tenacious_fetch(url);
}
