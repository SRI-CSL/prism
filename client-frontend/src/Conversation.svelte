<script>
 import { onMount, beforeUpdate, afterUpdate } from 'svelte'
 import { conversation, current_contact, registerContact } from './store';
 import { post_json } from './util';
 import Message from './Message.svelte';

 export let contact;

 let user_message = "";
 let message_input;

 let scrollable;
 let autoscroll;

 async function send(e) {
     if (user_message.length == 0) return;
     await post_json("/send", {
         address: contact,
         message: user_message
     });
     user_message = "";
     activate();
 }

 function activate() {
     registerContact(contact);
     $current_contact = contact;
     message_input.focus();
     scrollable.scrollTop = scrollable.scrollHeight;
 }

 onMount(activate);

 // Maintain scroll position when new messages come in
 beforeUpdate(() => { autoscroll = scrollable && (scrollable.offsetHeight + scrollable.scrollTop) > (scrollable.scrollHeight - 20); });
 afterUpdate(() => { if (autoscroll) scrollable.scrollTo(0, scrollable.scrollHeight); });
</script>

<div>
    <h1><span class="quiet">Conversation with</span> <span class="nobreak">{contact}</span></h1>
    <ul bind:this={scrollable}>
        <span class="dummy"/>
        {#each $conversation as message (message.nonce)}
            <Message {...message} />
        {/each}
    </ul>
    <form action="#" on:submit|preventDefault={send}>
        <input placeholder="Quick, say something smart!" bind:value={user_message} bind:this={message_input}>
    </form>
</div>

<style>
 div {
     flex: 1 0;
     display: flex;
     flex-direction: column;
     gap: 0.5em;
     height: 100%;
 }

 h1 {
     align-self: center;
     text-align: right;
     font-size: 1.5em;
     margin: 0
 }

 ul {
     flex: 1 1 auto;
     min-height: 0;
     padding: 0 0.2em;
     margin: 0;

     display: flex;
     flex-direction: column;
     gap: 0.4em;

     overflow-y: auto;
 }

 span {
     flex: 1 1 auto;
 }

 span.quiet {
     color: #666;
 }

 form {
     align-self: center;
     width: 100%;
 }

 input {
     width: 100%;
     padding: 10px;
     box-sizing: border-box;
 }
</style>
