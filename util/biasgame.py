from Utility import resources as ex
from module.keys import bias_game_location, idol_avatar_location
from PIL import Image


class BiasGame:
    async def create_bias_game_image(self, first_idol_id, second_idol_id):
        """Uses thread pool to create bias game image to prevent IO blocking."""
        (ex.thread_pool.submit(self.merge_images, first_idol_id, second_idol_id)).result()
        return f"{ bias_game_location}{first_idol_id}_{second_idol_id}.png"

    @staticmethod
    def merge_images(first_idol_id, second_idol_id):
        """Merge Idol Images if the merge doesn't exist already."""
        file_name = f"{first_idol_id}_{second_idol_id}.png"
        if not ex.check_file_exists(f"{ bias_game_location}{file_name}"):
            # open the images.
            versus_image = Image.open(f'{bias_game_location}versus.png')
            first_idol_image = Image.open(f'{idol_avatar_location}{first_idol_id}_IDOL.png')
            second_idol_image = Image.open(f'{ idol_avatar_location}{second_idol_id}_IDOL.png')

            # define the dimensions
            idol_image_width = 150
            idol_image_height = 150
            first_image_area = (0, 0)
            second_image_area = (versus_image.width - idol_image_width, 0)
            image_size = (idol_image_width, idol_image_height)

            # resize the idol images
            first_idol_image = first_idol_image.resize(image_size)
            second_idol_image = second_idol_image.resize(image_size)

            # add the idol images onto the VS image.
            versus_image.paste(first_idol_image, first_image_area)
            versus_image.paste(second_idol_image, second_image_area)

            # save the versus image.
            versus_image.save(f"{ bias_game_location}{file_name}")

    async def create_bias_game_bracket(self, all_games, user_id, bracket_winner):
        (ex.thread_pool.submit(self.create_bracket, all_games, user_id, bracket_winner)).result()
        return f"{ bias_game_location}{user_id}.png"

    @staticmethod
    def create_bracket(all_games, user_id, bracket_winner):
        def get_battle_images(idol_1_id, idol_2_id):
            return Image.open(f'{ idol_avatar_location}{idol_1_id}_IDOL.png'), Image.open(
                f'{ idol_avatar_location}{idol_2_id}_IDOL.png')

        def resize_images(first_img, second_img, first_img_size, second_img_size):
            return first_img.resize(first_img_size), second_img.resize(second_img_size)

        def paste_image(first_idol_img, second_idol_img, first_img_area, second_img_area):
            bracket.paste(first_idol_img, first_img_area)
            bracket.paste(second_idol_img, second_img_area)

        bracket = Image.open(f'{ bias_game_location}bracket8.png')
        count = 1
        for c_round in all_games:
            if len(c_round) <= 4:
                for battle in c_round:
                    first_idol, second_idol = battle[0], battle[1]
                    first_idol_info = ex.cache.stored_bracket_positions.get(count)
                    second_idol_info = ex.cache.stored_bracket_positions.get(count + 1)

                    # get images
                    first_idol_image, second_idol_image = get_battle_images(first_idol.id, second_idol.id)

                    # resize images
                    first_idol_image, second_idol_image = resize_images(first_idol_image, second_idol_image,
                                                                        first_idol_info.get('img_size'),
                                                                        second_idol_info.get('img_size'))

                    # paste image to bracket
                    paste_image(first_idol_image, second_idol_image, first_idol_info.get('pos'),
                                second_idol_info.get('pos'))

                    count = count + 2

        # add winner
        idol_info = ex.cache.stored_bracket_positions.get(count)
        idol_image = Image.open(f'{ idol_avatar_location}{bracket_winner.id}_IDOL.png')
        idol_image = idol_image.resize(idol_info.get('img_size'))
        bracket.paste(idol_image, idol_info.get('pos'))
        bracket.save(f"{ bias_game_location}{user_id}.png")
