<script>
 import { link, navigate } from "svelte-routing";
 import { contacts, current_contact, registerContact, unread_counts } from "./store";

 let new_contact = "";
 function add(e) {
     if(registerContact(new_contact)) {
         navigate(`/conversations/${new_contact}`);
         new_contact = "";
     }
 }
</script>

<div>
    <h3>Contacts</h3>
    <form on:submit|preventDefault={add}>
        <input placeholder="Add Contact" bind:value={new_contact}/>
    </form>
    <ul>
        {#each $contacts as contact (contact)}
            <li class:current="{contact === $current_contact}">
                <a href="/conversations/{contact}" use:link>{contact}</a>
                {#if $unread_counts[contact] }
                    <span class=unread>{$unread_counts[contact]}</span>
                {/if}
            </li>
        {/each}
    </ul>
</div>

<style>
 div {
     flex: 1 1 auto;
 }
 h3 {
     margin: 0.5em;
 }

 ul {
     display: flex;
     flex-direction: column;
     padding: 5px;
 }
 li {
     flex: 1 1 auto;
     list-style: none;
     display: flex;
     align-items: center;
 }


 li.current, li:hover {
     background-color: rgb(60, 160, 150);
 }

 li:hover {
    background-color: rgb(10, 100, 90);
 }

 a, a:visited {
     flex: 1 1 auto;
     text-decoration: none;
     color: white;
     width: 100%;
 }

 span.unread {
     height: 1.25em;
     min-width: 1.25em;
     line-height: 1.25em;
     padding: 0.1em;
     text-align: center;
     border-radius: 50%;
     font-weight: bold;
     background-color: rgb(210, 0, 0);
 }
</style>
