/*
 * Copyright (c) 2019-2023 SRI International.
 */

import { writable, derived, get } from 'svelte/store';
import { get_json } from "./util"

export const persona = await get_json("/persona");
export const contacts = writable(await get_json("/contacts"));
export const current_contact = writable(null);

const retrieved_messages = new Set();
export const messages = writable([]);
export const read_messages = writable({});
export const unread_messages = derived([messages, read_messages], ([$messages, $read_messages]) => {
  return $messages.filter(m => {
    return !(m.nonce in $read_messages);
  });
});
export const unread_counts = derived([contacts, unread_messages], ([$contacts, $unread_messages]) => {
  let count_map = {};
  for (const contact of $contacts) {
    count_map[contact] = $unread_messages.filter(m => m.sender == contact).length;
  }
  return count_map;
})

const lastNonce = derived(messages, $messages => $messages.at(-1)?.nonce);

function conversationWith(contact) {
  return derived(messages, $messages => {
    return $messages.filter(m => (m.sender == contact || m.receiver == contact));
  })
}

export const conversation = derived([messages, current_contact], ([$messages, $current_contact]) => {
  return $messages.filter(m => (m.sender == $current_contact || m.receiver == $current_contact));
})


export function registerContact(contact) {
  if (contact.length == 0 || contact == persona) return false;

  contacts.update($contacts => {
    if (!($contacts.includes(contact))) {
      console.log("Adding new contact " + contact);
      console.log("To contacts: " + $contacts);
      return $contacts.concat(contact);
    } else {
      return $contacts;
    }
  })

  return true;
}




async function fetchNewMessages() {
  const since = get(lastNonce);
  let params = since ? {since: since} : {};
  let fetched_messages = await get_json("/messages", params);
  let new_messages = fetched_messages.filter(m => !retrieved_messages.has(m.nonce));

  if (new_messages.length > 0) {
    for (const m of new_messages) {
      retrieved_messages.add(m.nonce);
    }
    messages.update($messages => $messages.concat(new_messages))
  }
}

const interval = setInterval(fetchNewMessages, 250)

// In development, unregister the message checker before doing a hot reload
if (import.meta.hot) {
  import.meta.hot.on('vite:beforeUpdate', (data) => clearInterval(interval));
}
