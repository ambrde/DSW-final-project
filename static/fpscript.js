$(document).ready(function(){
	$(".fa-heart").click(function(){
		$(this).toggleClass("fas far");
		$.post("/favorite", "contentId": contentId);
	});
});